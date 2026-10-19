"""
routes/diagnostics.py — API del panel de diagnóstico.

Permite ver desde la interfaz qué está haciendo Andromeda por dentro: qué
prompt recibió el modelo, si se buscó en internet y por qué, qué devolvió cada
motor, qué recuerdos se recuperaron y cuánto tardó cada paso.

El registro vive solo en memoria y está apagado por defecto.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.observability import diagnostics as diag

logger = logging.getLogger("andromeda.routes.diagnostics")
router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
async def get_state() -> JSONResponse:
    """Estado del registro y si el panel debe mostrarse.

    `available` decide si aparece la entrada en el menú. Se muestra cuando se
    arrancó con ANDROMEDA_DIAGNOSTICS=1 o cuando el registro ya está activo, de
    modo que la aplicación publicada no enseña el panel por defecto.
    """
    import os
    estado = diag.stats()

    # Versión publicada: el panel solo aparece al arrancar con
    # ANDROMEDA_DIAGNOSTICS=1 (o si el registro ya está activo). Expone los
    # prompts completos y variables de entorno: no debe verlo cualquiera.
    estado["available"] = (
        os.environ.get("ANDROMEDA_DIAGNOSTICS", "").lower() in ("1", "true", "on")
        or diag.is_enabled()
    )
    return JSONResponse(estado)


@router.put("")
async def set_state(request: Request) -> JSONResponse:
    """Activa o desactiva el registro. Al desactivar se vacía la memoria."""
    body = await request.json()
    activo = bool(body.get("enabled", False))
    diag.set_enabled(activo)
    diag.log("system", "registro de diagnóstico activado", level="success")
    return JSONResponse(diag.stats())


@router.get("/events")
async def get_events(since: int = 0, category: str = "", level: str = "") -> JSONResponse:
    """Eventos nuevos desde `since`.

    La interfaz sondea con el último número de secuencia que tiene, de forma que
    solo viaja lo nuevo en lugar del registro entero cada vez.
    """
    eventos = diag.get_events(since_seq=since, category=category, level=level)
    return JSONResponse({
        "events": eventos,
        "last_seq": eventos[-1]["seq"] if eventos else since,
        "enabled": diag.is_enabled(),
    })


@router.delete("/events")
async def clear_events() -> JSONResponse:
    """Vacía el registro. Útil antes de reproducir un fallo concreto."""
    diag.clear()
    return JSONResponse({"cleared": True})


@router.get("/export", response_class=PlainTextResponse)
async def export_text(request: Request) -> PlainTextResponse:
    """Registro completo en texto plano, listo para copiar o guardar.

    Incluye la foto del sistema al principio: sin saber qué hardware hay, qué
    modelos están cargados y qué capacidades están activas, el registro de
    eventos se interpreta a medias.
    """
    import json

    try:
        foto = (await snapshot(request)).body.decode("utf-8")
        cabecera = [
            "ESTADO DEL SISTEMA",
            "-" * 78,
            json.dumps(json.loads(foto), indent=2, ensure_ascii=False),
            "",
            "=" * 78,
            "EVENTOS",
            "",
        ]
    except Exception as exc:                              # noqa: BLE001
        cabecera = [f"(no se pudo obtener el estado del sistema: {exc})", ""]

    return PlainTextResponse(
        "\n".join(cabecera) + "\n" + diag.as_text(),
        headers={"Content-Disposition": 'attachment; filename="andromeda-diagnostico.txt"'},
    )


@router.get("/snapshot")
async def snapshot(request: Request) -> JSONResponse:
    """Foto del estado del sistema, sin depender de que el registro esté activo.

    Es lo primero que conviene mirar ante un fallo: responde a "¿está esto
    encendido?" para cada capacidad, en una sola llamada.
    """
    import os
    import sys

    st = request.app.state
    from app.core.flags import get_flag

    def _tiene(nombre: str) -> bool:
        return getattr(st, nombre, None) is not None

    try:
        modelos = list(getattr(getattr(st, "registry", None), "available_models", []) or [])
    except Exception:                                     # noqa: BLE001
        modelos = []

    mcp = getattr(st, "mcp_manager", None)
    try:
        conectados = list(getattr(mcp, "_clients", {}) or {}) if mcp else []
    except Exception:                                     # noqa: BLE001
        conectados = []

    return JSONResponse({
        "capacidades": {
            "red": get_flag(st.settings, "andromeda_network_egress"),
            "creacion_archivos": get_flag(st.settings, "andromeda_file_creation"),
            "memoria_semantica": _tiene("memory_store"),
            "perfil_memoria": _tiene("memory_profile"),
            "documentos_rag": _tiene("rag_index"),
            "skills": _tiene("skill_registry"),
        },
        "ollama": {
            "modelos": modelos,
            "url": getattr(st.settings, "ollama_base_url", ""),
            "keep_alive": os.environ.get("ANDROMEDA_KEEP_ALIVE", "30m"),
        },
        "memoria_por_significado": __import__("app.memory.semantic_setup", fromlist=["STATE"]).STATE,
        "mcp": {
            "conectados": conectados, "total": len(conectados),
            # Las integradas (archivos) están siempre; se cuentan aparte para no
            # confundirlas con conectores.
            "herramientas_integradas": sum(
                1 for t in (getattr(mcp, "tools", []) or [])
                if getattr(t, "server_id", "") == "builtin-fs") if mcp else 0,
            "bucle_de_herramientas_activo": bool(getattr(mcp, "has_external_tools", False)),
        },
        "buscador": {
            "searxng_propio": os.environ.get("ANDROMEDA_SEARXNG_URL", ""),
            "instancia_activa": getattr(
                __import__("app.core.web_search", fromlist=["x"]),
                "_searxng_working", None) or "",
        },
        "entorno": {
            "python": sys.version.split()[0],
            "plataforma": sys.platform,
            "empaquetada": bool(getattr(sys, "frozen", False)),
            "workspace": os.environ.get("ANDROMEDA_WORKSPACE", ""),
            "data_dir": os.environ.get("ANDROMEDA_DATA_DIR", ""),
            "idioma": os.environ.get("ANDROMEDA_LANGUAGE", ""),
            # Todas las variables ANDROMEDA_*: si algo está configurado de forma
            # rara, aquí se ve. Las que puedan llevar secretos se ocultan.
            "variables": {
                k: ("(oculto)" if any(x in k.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
                    else v)
                for k, v in sorted(os.environ.items())
                if k.startswith("ANDROMEDA_") or k.startswith("OLLAMA_")
            },
        },
        "hardware": _hardware(st),
        "recursos": _recursos(),
    })


def _hardware(st) -> dict:
    """Qué equipo detectó Andromeda: explica las decisiones de rendimiento."""
    hw = getattr(st, "hardware", None)
    if hw is None:
        return {}
    datos = {
        "cpu": getattr(hw, "cpu_model", ""),
        "nucleos": getattr(hw, "cpu_cores", 0),
        "ram_gb": getattr(hw, "ram_total_gb", 0),
        "vram_gb": getattr(hw, "total_vram_gb", 0),
        "aceleracion": getattr(hw, "acceleration", ""),
        "tier": getattr(hw, "max_tier", None),
    }
    # Y qué parámetros se derivan de ese hardware, que es lo que de verdad
    # llega a Ollama en cada petición.
    try:
        from app.core.inference_tuning import build_options, recommended_server_env
        datos["opciones_calculadas"] = build_options(
            {},
            vram_gb=float(datos["vram_gb"] or 0),
            ram_gb=float(datos["ram_gb"] or 0),
            cpu_cores=int(datos["nucleos"] or 0),
            acceleration=str(datos["aceleracion"] or ""),
        )
        datos["recomendado_en_ollama"] = recommended_server_env(
            float(datos["vram_gb"] or 0), str(datos["aceleracion"] or ""))
    except Exception:                                     # noqa: BLE001
        pass
    return datos


def _recursos() -> dict:
    """Uso de CPU y memoria del proceso: detecta fugas y saturación."""
    try:
        import psutil
        p = psutil.Process()
        return {
            "cpu_proceso_pct": p.cpu_percent(interval=0.1),
            "cpu_sistema_pct": psutil.cpu_percent(interval=0.1),
            "memoria_proceso_mb": round(p.memory_info().rss / 1024 / 1024, 1),
            "memoria_sistema_pct": psutil.virtual_memory().percent,
            "hilos": p.num_threads(),
            "descriptores": p.num_fds() if hasattr(p, "num_fds") else None,
        }
    except Exception:                                     # noqa: BLE001
        return {}
