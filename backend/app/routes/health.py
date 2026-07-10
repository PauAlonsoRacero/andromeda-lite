"""
health.py — Endpoints de salud y diagnóstico de Andromeda.

Endpoints:
  GET /api/health          → estado general (200 si OK, 503 si degradado)
  GET /api/health/hardware → HardwareInfo completo detectado al arranque
  GET /api/health/policy   → HardwarePolicy activa del tier actual
  GET /api/health/config   → configuración activa (sin secretos)
"""

import logging
import time
import asyncio

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.health")

router = APIRouter()

# Tiempo de arranque del servidor (para calcular uptime)
_start_time = time.time()


@router.get("")
async def health(request: Request) -> JSONResponse:
    """
    Estado general del sistema.

    Comprueba:
      - FastAPI responde (si llegamos aquí, sí)
      - Ollama es alcanzable (ping a /api/tags)
      - Al menos 1 especialista activo

    Returns:
        200 si todo OK
        503 si Ollama no responde o no hay especialistas activos
    """
    registry = request.app.state.registry
    hardware = request.app.state.hardware
    settings = request.app.state.settings

    # ── Ping a Ollama (auto-detecta URL que funciona, re-resuelve si falla) ────
    from app.ollama_resolver import resolve_ollama_url
    ollama_ok = False
    ollama_models = []
    # Probar primero la URL actual; si falla, re-resolver entre las candidatas
    working_url = await resolve_ollama_url(settings.ollama_base_url)
    if working_url:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.get(f"{working_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    ollama_ok = True
                    data = resp.json()
                    ollama_models = [m["name"] for m in data.get("models", [])]
                    # Persistir la URL que funciona para que chat/warmup la usen
                    settings.ollama_base_url = working_url
                    # Informar al registry de qué modelos hay descargados (para fallback)
                    try:
                        request.app.state.registry.set_available_models(ollama_models)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"Ollama no alcanzable: {exc}")

    # ── Estado de especialistas ───────────────────────────────────────────────
    status = registry.get_status_summary()
    specialists_active = status["active"]

    # ── Estado general ────────────────────────────────────────────────────────
    uptime_seconds = round(time.time() - _start_time, 0)

    if ollama_ok and specialists_active > 0:
        overall_status = "ok"
    elif ollama_ok and specialists_active == 0:
        overall_status = "degraded"   # Sistema arrancado pero sin especialistas
    else:
        overall_status = "down"       # Ollama no responde

    body = {
        "status": overall_status,
        "uptime_seconds": uptime_seconds,
        "hardware_tier": hardware.max_tier,
        "acceleration": hardware.acceleration,
        "ollama": {
            "reachable": ollama_ok,
            "url": settings.ollama_base_url,
            "models_available": len(ollama_models),
        },
        "specialists": {
            "active": specialists_active,
            "configured": status.get("active", 0),
            "total": status["total"],
            "pending": status["pending"],
        },
        "orchestrator_active": status["orchestrator_active"],
    }

    # Si no hay especialistas → 503 con instrucciones claras
    if overall_status in ("down", "degraded") and specialists_active == 0:
        body["hint"] = (
            "Configura al menos 1 especialista en config/specialists.yaml. "
            "Ejemplo: cambia model_name a 'mistral:7b' y active a true."
        )

    http_status = 200 if overall_status == "ok" else 503
    return JSONResponse(content=body, status_code=http_status)


@router.get("/hardware")
async def hardware_info(request: Request) -> JSONResponse:
    """
    Retorna el HardwareInfo completo detectado al arranque.
    Útil para la UI y para diagnosticar problemas de tier.
    """
    hardware = request.app.state.hardware
    return JSONResponse(content=hardware.model_dump())


@router.get("/hardware/live")
async def hardware_live(request: Request) -> JSONResponse:
    """Uso de RAM/VRAM en TIEMPO REAL (la UI lo sondea cada pocos segundos).
    A diferencia de /hardware (detectado al arranque), esto refleja la memoria
    libre ahora mismo, que cambia al cargar/descargar modelos en Ollama.
    """
    from app.hardware.detector import HardwareDetector
    try:
        usage = await asyncio.to_thread(HardwareDetector().live_usage)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    return JSONResponse(content=usage)


@router.get("/policy")
async def policy_info(request: Request) -> JSONResponse:
    """
    Retorna la HardwarePolicy activa para el tier actual.
    Muestra qué puede hacer el sistema con el hardware detectado.
    """
    hardware = request.app.state.hardware
    policy_engine = request.app.state.policy_engine
    policy = policy_engine.get_policy(hardware)
    return JSONResponse(content=policy.model_dump())


@router.get("/config")
async def config_info(request: Request) -> JSONResponse:
    """
    Retorna la configuración activa del sistema (sin datos sensibles).
    """
    settings = request.app.state.settings
    registry = request.app.state.registry

    return JSONResponse(content={
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "environment": settings.environment,
        "port": settings.port,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_timeout_seconds": settings.ollama_timeout_seconds,
        "default_temperature": settings.default_temperature,
        "default_max_tokens": settings.default_max_tokens,
        "max_parallel_specialists": settings.max_parallel_specialists,
        "telemetry_enabled": settings.telemetry_enabled,
        "specialists_status": registry.get_status_summary(),
    })


@router.get("/vram-plan")
async def vram_plan(request: Request) -> JSONResponse:
    """
    Muestra cuánta VRAM consumiría cada configuración posible de IAs.
    Útil para la UI al seleccionar cuántas IAs y qué nivel usar.

    Retorna:
      - VRAM libre actual
      - Para 1, 2, 3, 4 IAs: qué especialistas cabrían y con qué nivel
      - Política recomendada según hardware actual
    """
    try:
        registry     = request.app.state.registry
        hardware     = request.app.state.hardware
        policy_engine= request.app.state.policy_engine
    except AttributeError:
        # Fallback si no están inicializados (ej: en test)
        from app.hardware.detector import HardwareDetector
        detector = HardwareDetector()
        return JSONResponse(content={
            "vram_free_gb": detector.get_current_vram_free(),
            "vram_total_gb": detector.get_vram_info()['total_gb'],
            "hardware_tier": 1,
            "max_parallel_policy": 2,
            "plans": {
                "1": {"feasible": True, "vram_needed_gb": 5, "specialists": []},
                "2": {"feasible": True, "vram_needed_gb": 10, "specialists": []},
                "3": {"feasible": True, "vram_needed_gb": 15, "specialists": []},
                "4": {"feasible": True, "vram_needed_gb": 20, "specialists": []},
            },
            "recommended_n": 2,
        })

    # VRAM libre ahora mismo
    from app.hardware.detector import HardwareDetector
    detector   = HardwareDetector()
    vram_free  = detector.get_current_vram_free()
    if vram_free == 0 and hardware.acceleration == "cpu":
        vram_free = hardware.ram_available_gb * 0.4

    active = registry.get_eligible_for_tier(hardware.max_tier)
    base_policy = policy_engine.get_policy(hardware)

    plans = {}
    for n in [1, 2, 3, 4]:
        selected, total_vram, levels = policy_engine._fit_specialists_to_vram(
            specialists=active,
            max_count=n,
            vram_budget_gb=max(0, vram_free - 2.0),
            registry=registry,
            hardware_tier=hardware.max_tier,
            specialist_level_overrides={},
        )
        plans[str(n)] = {
            "fits":             len(selected) >= n or len(active) < n,
            "specialists":      [s.id for s in selected],
            "vram_needed_gb":   round(total_vram, 1),
            "vram_free_gb":     round(vram_free, 1),
            "levels_used":      levels,
            "feasible":         total_vram <= vram_free - 2.0,
        }

    return JSONResponse(content={
        "vram_free_gb":        round(vram_free, 1),
        "vram_total_gb":       hardware.total_vram_gb,
        "hardware_tier":       hardware.max_tier,
        "max_parallel_policy": base_policy.max_parallel,
        "plans":               plans,
        "recommended_n":       min(base_policy.max_parallel, len(active)),
    })


@router.get("/setup")
async def setup_status(request: Request) -> JSONResponse:
    """
    Estado de configuración inicial — para guiar al usuario en el primer arranque.
    Indica qué falta para que el sistema esté operativo.
    """
    settings = request.app.state.settings
    registry = request.app.state.registry

    # Modelos starter recomendados
    starter = {
        "phi3.5:3.8b":      "Orquestador, Verifier, Summarizer",
        "mistral:7b":       "Generalist",
        "qwen2.5-coder:7b": "Software Engineering",
    }

    installed = []
    ollama_ok = False

    # ── Detectar Ollama con el resolver robusto basado en urllib (stdlib). Esto
    # funciona en el .exe empaquetado donde httpx puede fallar por dependencias
    # ocultas que faltan. Devuelve URL + modelos en una sola pasada.
    from app.ollama_resolver import resolve_with_models, probe_sync
    ollama_url, installed = await resolve_with_models(preferred=settings.ollama_base_url)
    ollama_ok = ollama_url is not None

    # Último recurso síncrono directo (por si el to_thread fallara en el binario):
    if not ollama_ok:
        for _fb in ("http://127.0.0.1:11434", "http://localhost:11434"):
            _d = probe_sync(_fb, timeout=3.0)
            if _d is not None:
                ollama_ok = True
                ollama_url = _fb
                installed = [m.get("name", "") for m in _d.get("models", []) if m.get("name")]
                break

    # En la app de escritorio Ollama corre nativo (no en Docker), así que el
    # comando correcto es 'ollama pull'. En modo Docker, el contenedor lo expone
    # igualmente accesible vía 'ollama pull' si el CLI está instalado.
    import os as _os
    in_docker = _os.path.exists("/.dockerenv")
    def _pull_cmd(model: str) -> str:
        if in_docker:
            return f"docker exec andromeda-ollama ollama pull {model}"
        return f"ollama pull {model}"

    models_status = []
    for model, role in starter.items():
        is_installed = any(model in inst for inst in installed)
        models_status.append({
            "model": model, "role": role,
            "installed": is_installed,
            "pull_cmd": _pull_cmd(model),
        })

    active_specialists = len(registry.get_active())
    all_installed = all(m["installed"] for m in models_status)

    # Determinar el paso actual del onboarding
    if not ollama_ok:
        next_step = "ollama_offline"
    elif not any(m["installed"] for m in models_status):
        next_step = "download_models"
    elif active_specialists == 0:
        next_step = "activate_specialists"
    else:
        next_step = "ready"

    return JSONResponse(content={
        "ollama_reachable":   ollama_ok,
        "models":             models_status,
        "all_models_ready":   all_installed,
        "active_specialists": active_specialists,
        "next_step":          next_step,
        "is_ready":           next_step == "ready",
    })


@router.get("/diagnose")
async def diagnose(request: Request) -> JSONResponse:
    """
    Autodiagnóstico completo de la cadena de inferencia.

    Verifica, paso a paso, todo lo necesario para que "la IA funcione" y
    devuelve qué falla exactamente. Pensado para depurar en la máquina del
    usuario sin tener que leer logs.
    """
    settings = request.app.state.settings
    registry = request.app.state.registry
    checks: list[dict] = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    # 1. ¿Ollama responde? (detección stdlib robusta, reporta la URL encontrada)
    ollama_models: list[str] = []
    from app.ollama_resolver import resolve_with_models, CANDIDATE_URLS
    _ourl, ollama_models = await resolve_with_models(preferred=settings.ollama_base_url)
    if _ourl:
        add("Ollama conectado", True, f"{_ourl} · {len(ollama_models)} modelo(s)")
    else:
        add("Ollama conectado", False,
            f"sin respuesta en: {', '.join(CANDIDATE_URLS[:3])} — ¿está Ollama abierto?")

    # 2. ¿Hay modelos descargados?
    add("Modelos descargados en Ollama", len(ollama_models) > 0,
        ", ".join(ollama_models) if ollama_models else "ninguno — usa 'ollama pull <modelo>'")

    # 3. ¿Hay especialistas activos?
    try:
        active = [s for s in registry.get_all() if getattr(s, "active", False)]
        add("Especialistas activos", len(active) > 0,
            ", ".join(s.id for s in active) if active else "ninguno activo")
    except Exception as e:
        active = []
        add("Especialistas activos", False, f"{type(e).__name__}: {e}")

    # 4. ¿Los modelos de los especialistas activos están descargados?
    try:
        registry.set_available_models(ollama_models)
        missing = []
        for s in active:
            mname = getattr(s, "model_name", None)
            if mname and ollama_models and mname not in ollama_models:
                # ¿hay algún modelo de la misma familia?
                base = mname.split(":")[0]
                if not any(m.split(":")[0] == base for m in ollama_models):
                    missing.append(f"{s.id}→{mname}")
        add("Modelos de especialistas disponibles", len(missing) == 0,
            "todos disponibles" if not missing else f"faltan: {', '.join(missing)}")
    except Exception as e:
        add("Modelos de especialistas disponibles", False, f"{type(e).__name__}: {e}")

    # 5. Inferencia de prueba real (si hay al menos un modelo)
    test_model = ollama_models[0] if ollama_models else None
    if test_model:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={"model": test_model,
                          "messages": [{"role": "user", "content": "di hola"}],
                          "stream": False,
                          "options": {"num_predict": 10}},
                    timeout=60.0)
                if r.status_code == 200:
                    content = r.json().get("message", {}).get("content", "")
                    add("Inferencia de prueba", bool(content.strip()),
                        f"modelo {test_model} respondió: {content[:50]!r}")
                else:
                    add("Inferencia de prueba", False,
                        f"HTTP {r.status_code} con {test_model}")
        except Exception as e:
            add("Inferencia de prueba", False, f"{type(e).__name__}: {e}")
    else:
        add("Inferencia de prueba", False, "no hay modelos para probar")

    all_ok = all(c["ok"] for c in checks)
    return JSONResponse({
        "healthy": all_ok,
        "summary": ("Todo correcto" if all_ok
                    else "Hay problemas — revisa los checks marcados como ok=false"),
        "checks": checks,
    })
