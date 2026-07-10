"""
models.py — Gestión de especialistas en runtime + escritura en YAML.

Endpoints:
  GET  /api/models           → todos los especialistas
  GET  /api/models/active    → solo activos y configurados
  GET  /api/models/status    → resumen + ping a Ollama
  PUT  /api/models/{id}      → actualizar modelo — persiste en specialists.yaml
  POST /api/models/{id}/test → probar que el modelo responde
  GET  /api/models/ollama    → modelos disponibles en Ollama ahora mismo
"""

import logging
import time

import httpx
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger("andromeda.routes.models")

router = APIRouter()


class UpdateModelRequest(BaseModel):
    model_name: str
    active: bool = True


@router.get("")
async def get_all_models(request: Request) -> JSONResponse:
    registry = request.app.state.registry
    specialists = registry.get_all()
    return JSONResponse(content={
        "specialists": [s.model_dump() for s in specialists],
        "total": len(specialists),
    })


@router.get("/active")
async def get_active_models(request: Request) -> JSONResponse:
    registry = request.app.state.registry
    hardware  = request.app.state.hardware
    active    = registry.get_eligible_for_tier(hardware.max_tier)
    return JSONResponse(content={
        "specialists": [s.model_dump() for s in active],
        "count": len(active),
        "hardware_tier": hardware.max_tier,
    })


@router.get("/status")
async def get_models_status(request: Request) -> JSONResponse:
    registry = request.app.state.registry
    settings = request.app.state.settings

    ollama_ok = False
    available_models = []
    try:
        from app.ollama_resolver import resolve_ollama_url
        working_url = await resolve_ollama_url(settings.ollama_base_url)
        if working_url:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.get(
                    f"{working_url}/api/tags", timeout=5.0
                )
                if resp.status_code == 200:
                    ollama_ok = True
                    data = resp.json()
                    available_models = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass

    status = registry.get_status_summary()
    status["ollama_reachable"] = ollama_ok
    status["ollama_models"]    = available_models
    return JSONResponse(content=status)


@router.get("/ollama")
async def get_ollama_models(request: Request) -> JSONResponse:
    """Retorna los modelos disponibles en Ollama ahora mismo."""
    settings = request.app.state.settings
    from app.ollama_resolver import resolve_ollama_url
    working_url = await resolve_ollama_url(settings.ollama_base_url)
    if working_url:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.get(
                    f"{working_url}/api/tags", timeout=5.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return JSONResponse(content={
                        "models": models,
                        "count": len(models),
                        "reachable": True,
                        "url": working_url,
                    })
        except Exception:
            pass
    return JSONResponse(content={"models": [], "count": 0, "reachable": False})


@router.put("/{specialist_id}")
async def update_model(
    specialist_id: str,
    body: UpdateModelRequest,
    request: Request,
) -> JSONResponse:
    """
    Actualiza el modelo de un especialista.
    Persiste el cambio en specialists.yaml para que sobreviva reinicios.
    """
    registry = request.app.state.registry
    settings = request.app.state.settings

    try:
        # Actualizar en memoria
        updated = registry.update_model(
            specialist_id=specialist_id,
            model_name=body.model_name,
            active=body.active,
        )

        # CRÍTICO: el motor de chat resuelve el modelo vía get_model_override().
        # Sin esto, ignora la asignación y usa el modelo por defecto del nivel
        # (p.ej. llama3.2:3b), fallando si el usuario no lo tiene descargado.
        try:
            if body.active and body.model_name:
                registry.set_model_override(specialist_id, body.model_name)
            elif not body.active:
                registry.set_model_override(specialist_id, None)
        except Exception as _exc:
            logger.warning(f"No se pudo fijar override: {_exc}")

        # Persistir en specialists.yaml (ruta escribible si está definida)
        _wpath = getattr(settings, "specialists_writable_path", "") or settings.specialists_config_path
        _save_to_yaml(
            specialist_id=specialist_id,
            model_name=body.model_name,
            active=body.active,
            config_path=_wpath,
        )

        return JSONResponse(content={
            "success": True,
            "specialist": updated.model_dump(),
            "persisted": True,
            "message": "Guardado en specialists.yaml — cambio permanente.",
        })
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": True, "code": "NOT_FOUND", "message": str(exc)},
        )
    except Exception as exc:
        logger.error(f"Error guardando en YAML: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": f"Error al guardar: {exc}"},
        )


def _save_to_yaml(specialist_id: str, model_name: str, active: bool, config_path: str):
    """Escribe el cambio de modelo directamente en specialists.yaml."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"specialists.yaml no encontrado en {config_path}")
        return

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    specialists = data.get("specialists", [])
    updated = False

    for spec in specialists:
        if spec.get("id") == specialist_id:
            spec["model_name"] = model_name
            spec["active"] = active
            # CRÍTICO: el motor de chat elige un NIVEL (low/mid/high/ultra) y
            # usa levels[nivel].model_name, no spec.model_name. Si solo
            # cambiáramos model_name, el chat seguiría usando el modelo por
            # defecto del nivel (p.ej. llama3.2:3b) y fallaría si no lo tienes.
            # En Lite (un modelo por IA) ponemos el modelo elegido en TODOS los
            # niveles, así siempre se usa el que el usuario asignó.
            levels = spec.get("levels")
            if isinstance(levels, dict):
                for lvl in levels.values():
                    if isinstance(lvl, dict):
                        lvl["model_name"] = model_name
            updated = True
            break

    # Si no existía en el YAML, añadirlo
    if not updated:
        specialists.append({
            "id": specialist_id,
            "model_name": model_name,
            "active": active,
        })

    data["specialists"] = specialists

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info(f"specialists.yaml actualizado: {specialist_id} → {model_name} (active={active})")


@router.post("/{specialist_id}/test")
async def test_specialist(specialist_id: str, request: Request) -> JSONResponse:
    registry = request.app.state.registry
    settings = request.app.state.settings

    try:
        specialist = registry.get_by_id(specialist_id)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": True, "message": str(exc)})

    if specialist.model_name == "PENDIENTE_CONFIGURAR":
        return JSONResponse(status_code=400, content={
            "error": True,
            "code": "NOT_CONFIGURED",
            "message": "Asigna un modelo primero desde la pestaña Modelos.",
        })

    t_start = time.perf_counter()
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": specialist.model_name,
                    "messages": [
                        {"role": "system",  "content": specialist.system_prompt[:500]},
                        {"role": "user",    "content": "Responde en una frase: ¿cuál es tu especialidad?"},
                    ],
                    "options": {"temperature": 0.1, "num_predict": 80},
                    "stream": False,
                },
                timeout=30.0,
            )
            resp.raise_for_status()

        data      = resp.json()
        content   = data.get("message", {}).get("content", "")
        latency   = round((time.perf_counter() - t_start) * 1000, 0)

        return JSONResponse(content={
            "success": True,
            "specialist_id": specialist_id,
            "model_name": specialist.model_name,
            "response": content[:300],
            "latency_ms": latency,
        })

    except httpx.HTTPStatusError as exc:
        error = (
            f"Modelo '{specialist.model_name}' no encontrado. "
            f"Descárgalo con: ollama pull {specialist.model_name}"
            if exc.response.status_code == 404
            else f"HTTP {exc.response.status_code}"
        )
        return JSONResponse(status_code=503, content={
            "success": False, "specialist_id": specialist_id, "error": error,
        })
    except Exception as exc:
        return JSONResponse(status_code=503, content={
            "success": False, "specialist_id": specialist_id, "error": str(exc),
        })


@router.get("/warm-status")
async def get_warm_status(request: Request) -> JSONResponse:
    """
    Retorna qué modelos están actualmente cargados en VRAM (calientes).
    Usa el endpoint /api/ps de Ollama.
    """
    from app.core.warmup import check_warm_status
    settings = request.app.state.settings
    registry = request.app.state.registry
    loaded   = await check_warm_status(registry, settings.ollama_base_url)
    warm_ids = registry.get_warm_specialists()
    return JSONResponse(content={
        "loaded_in_vram": loaded,
        "configured_warm": warm_ids,
        "count_hot": len(loaded),
    })


@router.get("/levels/{specialist_id}")
async def get_specialist_levels(specialist_id: str, request: Request) -> JSONResponse:
    """
    Retorna los 4 niveles de potencia de un especialista y
    cuál se usaría con el hardware actual.
    """
    registry = request.app.state.registry
    hardware = request.app.state.hardware

    try:
        registry.get_by_id(specialist_id)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    tiers = registry.get_tiers(specialist_id)
    if not tiers:
        return JSONResponse(content={
            "specialist_id": specialist_id,
            "levels": None,
            "message": "Este especialista no tiene sistema de niveles configurado",
        })

    current_model, current_level = registry.resolve_model_for_tier(
        specialist_id,
        hardware.max_tier,
        hardware.total_vram_gb * 0.8,
    )

    forced = registry.get_forced_level(specialist_id)

    return JSONResponse(content={
        "specialist_id":  specialist_id,
        "hardware_tier":  hardware.max_tier,
        "vram_total_gb":  hardware.total_vram_gb,
        "active_model":   current_model,
        "active_level":   current_level,
        "forced_level":   forced,
        "auto_selection": forced is None,
        "levels": {
            name: {
                "model_name":      lv.model_name,
                "params_b":        lv.params_b,
                "vram_required_gb":lv.vram_required_gb,
                "min_tier":        lv.min_tier,
                "description":     lv.description,
                "available":       lv.min_tier <= hardware.max_tier and lv.vram_required_gb <= hardware.total_vram_gb * 0.85,
            }
            for name, lv in [("low", tiers.low), ("mid", tiers.mid),
                              ("high", tiers.high), ("ultra", tiers.ultra)]
            if lv
        },
    })


@router.put("/levels/{specialist_id}/force")
async def set_forced_level(specialist_id: str, request: Request) -> JSONResponse:
    """
    Fuerza un nivel específico para un especialista.
    Body: {"level": "low"|"mid"|"high"|"ultra"|null}
    null = volver a selección automática
    """
    registry = request.app.state.registry
    body = await request.json()
    level = body.get("level")  # None = automático

    try:
        registry.get_by_id(specialist_id)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    registry.set_forced_level(specialist_id, level)

    return JSONResponse(content={
        "success": True,
        "specialist_id": specialist_id,
        "forced_level": level,
        "mode": "automático" if level is None else f"forzado a {level}",
    })


@router.post("/unload")
async def unload_models(request: Request) -> JSONResponse:
    """
    Descarga modelos de la VRAM (los "apaga"). Útil al cambiar de IA: el modelo
    viejo debe dejar de estar caliente.

    Body opcional:
      {"models": ["mistral:7b", ...]}  → descarga esos modelos concretos
      {}  o  {"all": true}             → descarga todos los que estén cargados

    Implementación: Ollama descarga un modelo de VRAM con una petición de
    generación vacía y keep_alive=0.
    """
    import httpx
    settings = request.app.state.settings
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    targets = body.get("models") or []
    # Si no se especifican, descargar todos los cargados ahora mismo
    if not targets:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                r = await client.get(f"{settings.ollama_base_url}/api/ps", timeout=5.0)
                if r.status_code == 200:
                    targets = [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        except Exception as exc:
            return JSONResponse(status_code=502, content={"error": f"No se pudo consultar Ollama: {exc}"})

    targets = [t for t in targets if t]
    unloaded = []
    async with httpx.AsyncClient(trust_env=False) as client:
        for model in targets:
            try:
                # keep_alive=0 → Ollama libera el modelo de VRAM inmediatamente
                await client.post(
                    f"{settings.ollama_base_url}/api/generate",
                    json={"model": model, "keep_alive": 0, "prompt": ""},
                    timeout=10.0,
                )
                unloaded.append(model)
            except Exception:
                pass

    return JSONResponse(content={"success": True, "unloaded": unloaded})


@router.put("/warm/{specialist_id}")
async def set_warm(specialist_id: str, request: Request) -> JSONResponse:
    """
    Activa o desactiva el precalentamiento de un especialista.
    Body: {"warm": true|false}
    """
    from app.core.warmup import warmup_models
    registry = request.app.state.registry
    hardware = request.app.state.hardware
    body = await request.json()
    warm = bool(body.get("warm", False))

    try:
        registry.get_by_id(specialist_id)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    registry.set_warm(specialist_id, warm)

    if warm:
        import asyncio
        asyncio.create_task(warmup_models(
            registry=registry,
            ollama_url=request.app.state.settings.ollama_base_url,
            hardware_tier=hardware.max_tier,
        ))

    return JSONResponse(content={
        "success": True,
        "specialist_id": specialist_id,
        "keep_warm": warm,
    })


@router.get("/catalog")
async def model_catalog(request: Request, q: str = "", quant: str = "Q4") -> JSONResponse:
    """
    Catálogo de modelos de Ollama para buscar y descargar.
    Cada modelo incluye: tier, VRAM estimada, GPUs de referencia,
    y — si se detecta tu hardware — velocidad estimada y si cabe en tu GPU.
    """
    from ..core.model_catalog import get_catalog, lookup_bandwidth

    # Detectar hardware del usuario (guardado al arranque)
    user_bandwidth = 0.0
    user_vram = 0.0
    try:
        hardware = request.app.state.hardware
        if hardware and hardware.gpus:
            gpu = hardware.gpus[0]  # GPU principal
            user_vram = gpu.get("vram_total_gb", 0.0)
            user_bandwidth = lookup_bandwidth(gpu.get("name", ""))
    except Exception:
        pass

    models = get_catalog(q, quant, user_bandwidth, user_vram)
    return JSONResponse(content={
        "models": models,
        "hardware_detected": user_vram > 0,
        "user_vram_gb": user_vram,
        "user_bandwidth_gbs": user_bandwidth,
    })


# Progreso de descargas en curso: {model: {status, pct, total_mb, done_mb}}
_pull_jobs: dict[str, dict] = {}


@router.post("/pull")
async def pull_model(request: Request) -> JSONResponse:
    """
    Descarga un modelo de Ollama (ollama pull) con tracking de progreso.
    Body: {"model_name": "qwen2.5-coder:7b"}
    Progreso: GET /api/models/pull-progress/{model_name}
    """
    import httpx
    body = await request.json()
    model_name = body.get("model_name", "").strip()
    if not model_name:
        return JSONResponse(content={"error": "model_name requerido"}, status_code=400)

    # Resolver URL de Ollama
    try:
        from ..ollama_resolver import resolve_ollama_url
        base_url = await resolve_ollama_url()
    except Exception:
        base_url = request.app.state.settings.ollama_base_url

    _pull_jobs[model_name] = {"status": "iniciando", "pct": 0, "total_mb": 0, "done_mb": 0}

    async def do_pull():
        import json as _json
        layers: dict[str, tuple[int, int]] = {}   # digest -> (completed, total)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=15.0), trust_env=False) as client:
                async with client.stream("POST", f"{base_url}/api/pull",
                                          json={"name": model_name}) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            d = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        status = d.get("status", "")
                        digest = d.get("digest", "")
                        total = d.get("total", 0)
                        completed = d.get("completed", 0)
                        if digest and total:
                            layers[digest] = (completed, total)
                        sum_done = sum(c for c, _ in layers.values())
                        sum_total = sum(t for _, t in layers.values())
                        pct = round(sum_done / sum_total * 100, 1) if sum_total else 0
                        _pull_jobs[model_name] = {
                            "status": status or "descargando",
                            "pct": pct,
                            "total_mb": round(sum_total / 1024 / 1024),
                            "done_mb": round(sum_done / 1024 / 1024),
                        }
                        if status == "success":
                            _pull_jobs[model_name]["pct"] = 100
                            _pull_jobs[model_name]["status"] = "completado"
        except Exception as exc:
            _pull_jobs[model_name] = {"status": f"error: {str(exc)[:80]}",
                                      "pct": -1, "total_mb": 0, "done_mb": 0}

    import asyncio
    asyncio.create_task(do_pull())
    return JSONResponse(content={"status": "descargando", "model": model_name,
                                 "message": f"Descarga de {model_name} iniciada."})


@router.get("/pull-progress/{model_name:path}")
async def pull_progress(model_name: str) -> JSONResponse:
    """Progreso de la descarga de un modelo: pct (0-100, -1=error), MB."""
    job = _pull_jobs.get(model_name)
    if not job:
        return JSONResponse(content={"status": "desconocido", "pct": 0,
                                     "total_mb": 0, "done_mb": 0})
    return JSONResponse(content=job)


@router.post("/auto-classify")
async def auto_classify(request: Request) -> JSONResponse:
    """
    Dado un modelo (params o nombre), devuelve tier, VRAM, GPUs de referencia
    y — si hay hardware detectado — velocidad estimada y si cabe en tu GPU.
    Body: {"params_b": 7} o {"model_name": "qwen2.5-coder:7b"}
    """
    from ..core.model_catalog import (classify_tier, estimate_vram, CATALOG,
                                       TIER_INFO, estimate_tokens_per_sec, lookup_bandwidth)
    body = await request.json()
    params_b = body.get("params_b", 0)
    model_name = body.get("model_name", "")

    # Si dan nombre, buscar en catálogo
    if model_name and not params_b:
        for m in CATALOG:
            if m["name"] == model_name:
                params_b = m["params_b"]
                break
        # Intentar extraer de "modelo:7b"
        if not params_b and ":" in model_name:
            suffix = model_name.split(":")[-1].lower().replace("b", "")
            try: params_b = float(suffix)
            except ValueError: params_b = 0

    vram = estimate_vram(params_b)
    tier = classify_tier(params_b, vram)
    info = TIER_INFO[tier]

    result = {
        "params_b": params_b,
        "vram_estimated_gb": vram,
        "tier": tier,
        "tier_name": info["name"],
        "tier_vram_range": info["vram_range"],
        "tier_desc": info["desc"],
        "gpus_desktop": info["gpus_desktop"],
        "gpus_laptop": info["gpus_laptop"],
    }

    # Datos según hardware del usuario
    try:
        hardware = request.app.state.hardware
        if hardware and hardware.gpus:
            gpu = hardware.gpus[0]
            user_vram = gpu.get("vram_total_gb", 0.0)
            bw = lookup_bandwidth(gpu.get("name", ""))
            if bw > 0:
                tps = estimate_tokens_per_sec(params_b, bw)
                result["est_tokens_per_sec"] = tps
            if user_vram > 0:
                result["fits_in_vram"] = vram <= user_vram
                result["vram_headroom_gb"] = round(user_vram - vram, 1)
    except Exception:
        pass

    return JSONResponse(content=result)


@router.post("/bake-identity")
async def bake_identity(request: Request) -> JSONResponse:
    """
    Crea una variante del modelo con la identidad de Andromeda GRABADA dentro
    (vía Modelfile de Ollama). Mucho más difícil de saltar que un system prompt.
    Body: {"model_name": "qwen2.5-coder:7b",
           "topic": "ciberseguridad",          (opcional)
           "instructions": "...",               (opcional)
           "specialist_id": "generalist"}       (opcional, lee el rol guardado)
    Si se da topic (o un specialist_id con rol asignado), se hornea también
    la especialización y la variante lleva sufijo del topic.
    """
    import httpx
    import re
    from ..specialists.identity import ANDROMEDA_IDENTITY
    from ..specialists.custom_roles import get_role, build_specialization

    body = await request.json()
    model_name = body.get("model_name", "").strip()
    if not model_name:
        return JSONResponse(content={"error": "model_name requerido"}, status_code=400)
    if model_name.endswith("-andromeda") or "-andromeda-" in model_name:
        return JSONResponse(content={"variant": model_name, "message": "Ya es una variante Andromeda."})

    topic = body.get("topic", "").strip()
    instructions = body.get("instructions", "").strip()

    # Si dan specialist_id y no topic explícito, leer el rol guardado
    specialist_id = body.get("specialist_id", "").strip()
    if specialist_id and not topic:
        role = get_role(specialist_id)
        if role:
            topic = role.get("topic", "")
            instructions = role.get("instructions", "")

    # Construir el system: identidad + (especialización si hay topic)
    system_parts = ANDROMEDA_IDENTITY
    if topic:
        system_parts += build_specialization(topic, instructions)
    system_line = system_parts.replace("\n", " ").replace('"', "'").strip()

    # Nombre de la variante: incluye el topic si lo hay (slug limpio)
    if topic:
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:24]
        variant = f"{model_name}-andromeda-{slug}"
    else:
        variant = model_name + "-andromeda"

    modelfile = f'FROM {model_name}\nSYSTEM """{system_line}"""\nPARAMETER temperature 0.7\nPARAMETER top_p 0.9'

    try:
        from ..ollama_resolver import resolve_ollama_url
        base_url = await resolve_ollama_url()
    except Exception:
        base_url = request.app.state.settings.ollama_base_url

    async def do_create():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=15.0), trust_env=False) as client:
                async with client.stream("POST", f"{base_url}/api/create",
                                          json={"name": variant, "modelfile": modelfile}) as resp:
                    async for _ in resp.aiter_lines():
                        pass
        except Exception:
            pass

    import asyncio
    asyncio.create_task(do_create())

    msg = f"Creando {variant} con identidad grabada"
    if topic:
        msg += f" y especialización en «{topic}»"
    msg += ". Asígnalo a un especialista cuando termine."
    return JSONResponse(content={"variant": variant, "topic": topic or None, "message": msg})


@router.get("/recommended-setup")
async def recommended_setup(request: Request) -> JSONResponse:
    """
    Recomendación de modelos y variantes según el hardware y caso de uso.
    Devuelve: qué descargar, qué variantes crear, en qué orden.
    """
    from ..specialists.personality_profiles import get_all_personalities
    import psutil
    
    # Detectar VRAM disponible aproximadamente
    cpu_count = psutil.cpu_count()
    memory_gb = psutil.virtual_memory().total / (1024**3)
    
    # Sugerencias por capacidad
    if memory_gb >= 32 and cpu_count >= 12:
        # Setup premium: 3 modelos, 6 variantes
        setup = "premium"
        models = [
            {"name": "qwen2.5-coder:7b", "description": "Código (base)", "vram": 5, "purpose": "Engineer + Reviewer"},
            {"name": "llama3.1:8b", "description": "Generalista (base)", "vram": 6, "purpose": "Generalist + DevOps + Writer"},
            {"name": "mistral:7b", "description": "Análisis (base)", "vram": 5, "purpose": "Analyst"},
        ]
    elif memory_gb >= 16:
        # Setup estándar: 2 modelos, 4-5 variantes
        setup = "standard"
        models = [
            {"name": "qwen2.5-coder:7b", "description": "Código (base)", "vram": 5, "purpose": "Engineer + Reviewer"},
            {"name": "llama3.1:8b", "description": "Generalista (base)", "vram": 6, "purpose": "Generalist + DevOps + Writer"},
        ]
    else:
        # Setup ligero: 1-2 modelos, 2-3 variantes
        setup = "lite"
        models = [
            {"name": "mistral:7b", "description": "Modelo eficiente", "vram": 5, "purpose": "Generalist + Engineer"},
        ]
    
    personalities = get_all_personalities()
    
    return JSONResponse(content={
        "setup": setup,
        "hardware": {"memory_gb": round(memory_gb), "cpu_count": cpu_count},
        "models_to_download": models,
        "total_vram_recommended": sum(m["vram"] for m in models),
        "variants_to_create": [
            {
                "variant": k,
                "name": v["name"],
                "role": v["role"],
                "from_base": "ej: qwen2.5-coder:7b (ver arriba)"
            }
            for k, v in personalities.items()
        ],
        "note": "Descarga los modelos con Ollama, luego ejecuta GRABAR-VARIANTES-ESPECIALIZADAS.ps1"
    })


@router.get("/role/{specialist_id}")
async def get_custom_role(specialist_id: str) -> JSONResponse:
    """Devuelve el rol/topic personalizado de un especialista."""
    from ..specialists.custom_roles import get_role
    role = get_role(specialist_id)
    return JSONResponse(content={"specialist_id": specialist_id, "role": role})


@router.put("/role/{specialist_id}")
async def set_custom_role(specialist_id: str, request: Request) -> JSONResponse:
    """
    Asigna un topic + instrucciones a un especialista, especializándolo.
    Body: {"topic": "ciberseguridad", "instructions": "Enfócate en pentesting..."}
    """
    from ..specialists.custom_roles import set_role
    body = await request.json()
    topic = body.get("topic", "").strip()
    instructions = body.get("instructions", "").strip()
    if not topic:
        return JSONResponse(content={"error": "topic requerido"}, status_code=400)
    role = set_role(specialist_id, topic, instructions)
    return JSONResponse(content={"specialist_id": specialist_id, "role": role,
                                 "message": f"Especialista enfocado en: {topic}"})


@router.delete("/role/{specialist_id}")
async def clear_custom_role(specialist_id: str) -> JSONResponse:
    """Elimina el rol personalizado de un especialista."""
    from ..specialists.custom_roles import clear_role
    clear_role(specialist_id)
    return JSONResponse(content={"specialist_id": specialist_id, "message": "Rol personalizado eliminado"})
