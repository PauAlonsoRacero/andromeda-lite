"""
mcp.py — Endpoints de MCP de Andromeda.

GET  /api/mcp/status          → estado de todos los servidores MCP
GET  /api/mcp/tools           → lista de todas las herramientas disponibles
POST /api/mcp/call            → ejecutar una herramienta directamente
POST /api/mcp/reload          → reconectar todos los servidores
GET  /api/mcp/servers         → configuración de servidores
PUT  /api/mcp/servers/{id}    → habilitar/deshabilitar un servidor
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.mcp")
router = APIRouter()


@router.get("/status")
async def mcp_status(request: Request) -> JSONResponse:
    """Estado completo del sistema MCP."""
    manager = getattr(request.app.state, 'mcp_manager', None)
    if not manager:
        return JSONResponse(content={
            "enabled": False,
            "message": "MCP no inicializado",
            "total_tools": 0,
            "servers": {},
        })
    summary = manager.get_tools_summary()
    summary["enabled"] = True
    return JSONResponse(content=summary)


@router.get("/tools")
async def list_tools(request: Request) -> JSONResponse:
    """Lista todas las herramientas MCP disponibles."""
    manager = getattr(request.app.state, 'mcp_manager', None)
    if not manager:
        return JSONResponse(content={"tools": [], "count": 0})

    tools = [t.to_dict() for t in manager.tools]
    return JSONResponse(content={"tools": tools, "count": len(tools)})


@router.post("/call")
async def call_tool(request: Request) -> JSONResponse:
    """
    Ejecuta una herramienta MCP directamente.
    Útil para testing y para la UI de Modelos.

    Body: {"tool": "read_file", "arguments": {"path": "/tmp/x"}, "server_id": null}
    """
    manager = getattr(request.app.state, 'mcp_manager', None)
    if not manager:
        return JSONResponse(status_code=503, content={"error_key": "err.mcp_unavailable"})

    body      = await request.json()
    tool_name = body.get("tool")
    arguments = body.get("arguments", {})
    server_id = body.get("server_id")

    if not tool_name:
        return JSONResponse(status_code=400, content={"error_key": "err.tool_required"})

    result = await manager.call_tool(tool_name, arguments, server_id)

    return JSONResponse(content={
        "tool":      result.tool_name,
        "server_id": result.server_id,
        "content":   result.content,
        "text":      result.text,
        "is_error":  result.is_error,
        "error_msg": result.error_msg if result.is_error else None,
    })


@router.post("/chat")
async def mcp_chat(request: Request) -> JSONResponse:
    """
    Chat con acceso a herramientas MCP.
    El modelo decide qué herramientas usar y las ejecuta automáticamente.

    Body: {
        "prompt": "Lee el archivo README.md",
        "model": "mistral:7b",
        "specialist": "generalist"
    }
    """
    from app.mcp.executor import MCPExecutor

    manager   = getattr(request.app.state, 'mcp_manager', None)
    registry  = request.app.state.registry
    settings  = request.app.state.settings

    if not manager or not manager.tools:
        return JSONResponse(status_code=503, content={
            "error": "MCP no disponible o sin herramientas. Habilita servidores en config/mcp_servers.yaml"
        })

    body          = await request.json()
    prompt        = body.get("prompt", "")
    specialist_id = body.get("specialist", "generalist")

    if not prompt:
        return JSONResponse(status_code=400, content={"error_key": "err.prompt_required"})

    try:
        specialist = registry.get_by_id(specialist_id)
        model_name = specialist.model_name
    except Exception:
        model_name = "mistral:7b"
        system_prompt = "Eres un asistente útil con acceso a herramientas del sistema."

    try:
        system_prompt = specialist.system_prompt
    except Exception:
        system_prompt = "Eres un asistente útil."

    executor = MCPExecutor(manager)
    response, tool_calls = await executor.run_with_tools(
        prompt=prompt,
        model_name=model_name,
        system_prompt=system_prompt,
        ollama_url=settings.ollama_base_url,
    )

    return JSONResponse(content={
        "response":   response,
        "tool_calls": tool_calls,
        "model":      model_name,
        "specialist": specialist_id,
    })


@router.post("/reload")
async def reload_mcp(request: Request) -> JSONResponse:
    """Reconecta todos los servidores MCP."""
    manager = getattr(request.app.state, 'mcp_manager', None)
    if not manager:
        return JSONResponse(status_code=503, content={"error_key": "err.mcp_not_ready"})

    await manager.shutdown()
    await manager.initialize()
    summary = manager.get_tools_summary()
    return JSONResponse(content={"success": True, **summary})


@router.get("/servers")
async def list_servers(request: Request) -> JSONResponse:
    """
    Lista TODOS los servidores configurados en mcp_servers.yaml,
    con su estado enabled y si están conectados.
    """
    import yaml
    from pathlib import Path

    from app.mcp import secrets_store

    settings = request.app.state.settings
    manager  = getattr(request.app.state, 'mcp_manager', None)

    # Ruta del YAML — robusta para binario (.app/.exe), Docker y desarrollo.
    cfg_path = getattr(settings, 'mcp_servers_path', None)
    path = Path(cfg_path) if cfg_path else None
    if not path or not path.exists():
        # Buscar en las mismas ubicaciones que el resto de configs
        import sys as _sys
        candidates = []
        mp = getattr(_sys, "_MEIPASS", None)
        if mp:
            candidates.append(Path(mp) / "config" / "mcp_servers.yaml")
        if getattr(_sys, "frozen", False):
            candidates.append(Path(_sys.executable).resolve().parent / "config" / "mcp_servers.yaml")
        here = Path(__file__).resolve()
        candidates.append(here.parents[3] / "config" / "mcp_servers.yaml")  # <repo>/config
        candidates.append(Path("config/mcp_servers.yaml"))
        candidates.append(Path("/config/mcp_servers.yaml"))
        for cand in candidates:
            if cand.exists():
                path = cand
                break

    servers = []
    if path and path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = __import__('app.mcp.state', fromlist=['apply']).apply(yaml.safe_load(f) or {})
            connected = {}
            if manager:
                summary = manager.get_tools_summary()
                connected = summary.get("servers", {})
            for sid, cfg in (data.get("servers", {}) or {}).items():
                conn = connected.get(sid, {})
                servers.append({
                    "id": sid,
                    "label": cfg.get("label", sid),
                    "enabled": cfg.get("enabled", False),
                    "description": cfg.get("description", ""),
                    "install": cfg.get("install", ""),
                    "requires_key": cfg.get("requires_key", []),
                    # Qué claves ya están configuradas, para que la UI muestre
                    # el estado real en vez de pedirlas siempre. Nunca se
                    # devuelve el valor de una clave, solo si existe.
                    "keys_status": secrets_store.status(cfg.get("requires_key", []) or []),
                    "docs": cfg.get("docs", ""),
                    # Conectores que necesitan preparación fuera de Andromeda
                    # (Gmail, WhatsApp) y los de riesgo alto (WhatsApp no oficial).
                    "setup": cfg.get("setup", "auto"),
                    "risk": cfg.get("risk", "normal"),
                    "connected": conn.get("connected", False),
                    "tools": conn.get("tools", []),
                    "tool_count": conn.get("count", 0),
                    # Motivo del fallo, si lo hubo: sin esto el usuario solo ve
                    # "sin conectar" y no sabe qué hacer al respecto.
                    "error": (manager.last_error(sid) if manager else ""),
                })
        except Exception as exc:
            logger.error(f"Error leyendo mcp_servers.yaml: {exc}")

    return JSONResponse(content={"servers": servers, "count": len(servers)})


@router.put("/servers/{server_id}")
async def toggle_server(server_id: str, request: Request) -> JSONResponse:
    """
    Activa o desactiva un servidor MCP en el YAML.
    Body: {"enabled": true/false}
    """
    import yaml
    from pathlib import Path

    body = await request.json()
    enabled = bool(body.get("enabled", False))

    settings = request.app.state.settings
    cfg_path = getattr(settings, 'mcp_servers_path', None) or "/config/mcp_servers.yaml"
    path = Path(cfg_path)
    if not path.exists():
        path = Path("config/mcp_servers.yaml")

    if not path.exists():
        return JSONResponse(status_code=404, content={
            "error": True, "message": "mcp_servers.yaml no encontrado"
        })

    try:
        with path.open("r", encoding="utf-8") as f:
            data = __import__('app.mcp.state', fromlist=['apply']).apply(yaml.safe_load(f) or {})
        if server_id not in (data.get("servers", {}) or {}):
            return JSONResponse(status_code=404, content={
                "error": True, "message": f"Servidor '{server_id}' no existe"
            })
        data["servers"][server_id]["enabled"] = enabled
        # Estado en la carpeta de datos del usuario, no en el YAML de la app
        # (en Windows está en Program Files y no se puede escribir).
        from app.mcp import state as _mcp_state
        _mcp_state.set_enabled(server_id, enabled)

        # Aplicar AL INSTANTE: al activar, conectamos ese servidor (npx/uvx lo
        # descarga solo la primera vez); al desactivar, lo desconectamos. Sin
        # necesidad de pulsar "Reconectar".
        manager = getattr(request.app.state, 'mcp_manager', None)
        result = {}
        install_note = ""
        if manager:
            if enabled:
                # Plug and play: si al servidor le falta su runtime (npx/uvx),
                # se intenta instalar antes de conectar en lugar de fallar y
                # dejar al usuario con instrucciones de terminal.
                from app.mcp import runtime_installer as ri
                ri.ensure_path_in_environ()
                srv_cfg = (data.get("servers", {}) or {}).get(server_id, {}) or {}
                runtime = ri.runtime_for_command(srv_cfg.get("command", []))
                if runtime and not ri.is_available(runtime):
                    logger.info(f"MCP [{server_id}]: falta '{runtime}', instalando…")
                    outcome = await ri.install_runtime(runtime)
                    install_note = outcome["message"]
                    if not outcome["ok"]:
                        # No se pudo instalar solo: se informa con la instrucción
                        # exacta y no se intenta conectar (fallaría igualmente).
                        return JSONResponse(content={
                            "success": True, "server_id": server_id, "enabled": enabled,
                            "connected": False, "tools": [], "tool_count": 0,
                            "needs_runtime": runtime, "manual_install": outcome["manual"],
                            "message": outcome["message"],
                        })
                result = await manager.connect_one(server_id)
            else:
                result = await manager.disconnect_one(server_id)

        ok = result.get("connected", False)

        # Si se pidió activar pero no conectó, revertir el flag en el YAML: un
        # servidor marcado como "activado" que en realidad no funciona es un
        # estado mentiroso que confunde en cada arranque posterior.
        if enabled and not ok:
            try:
                from app.mcp import state as _mcp_state
                _mcp_state.set_enabled(server_id, False)
            except Exception as exc:                       # noqa: BLE001
                logger.warning(f"No se pudo revertir 'enabled' de {server_id}: {exc}")

        # Clave traducible además del texto: la interfaz mostraba siempre
        # "Conectado — N herramientas." en español, fuera cual fuera el idioma.
        if enabled and not ok:
            message = result.get("error") or "No se pudo conectar."
            message_key = None if result.get("error") else "mcp.msg_failed"
        elif enabled:
            message = f"Conectado — {result.get('count', 0)} herramientas."
            message_key = "mcp.msg_connected"
        else:
            message = "Desactivado."
            message_key = "mcp.msg_disabled"
        if install_note and enabled:
            message = f"{install_note} {message}"

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            # Refleja el estado REAL tras el intento, no lo que se pidió.
            "enabled": enabled and ok if enabled else False,
            "connected": ok,
            "tools": result.get("tools", []),
            "tool_count": result.get("count", 0),
            "needs_key": result.get("needs_key", []),
            "message": message,
            "message_key": message_key,
            "message_args": {"count": result.get("count", 0)},
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={
            "error": True, "message": f"Error: {exc}"
        })


# ── Claves de API de los servidores MCP ─────────────────────────────────────

@router.get("/keys")
async def list_keys() -> JSONResponse:
    """Nombres de las claves configuradas. Nunca devuelve sus valores."""
    from app.mcp import secrets_store
    return JSONResponse(content={"configured": secrets_store.list_configured()})


@router.put("/keys/{key_name}")
async def set_key(key_name: str, request: Request) -> JSONResponse:
    """Guarda una clave de API y la aplica al proceso en curso.

    Se guarda en el directorio de datos del usuario con permisos 0600, de modo
    que no hace falta exportar variables de entorno antes de abrir la app.
    """
    from app.mcp import secrets_store
    body = await request.json()
    value = (body.get("value") or "").strip()
    if not value:
        return JSONResponse(status_code=400, content={"error_key": "err.value_empty"})
    try:
        secrets_store.set_key(key_name, value)
    except (ValueError, RuntimeError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(content={"saved": True, "key": key_name})


@router.delete("/keys/{key_name}")
async def delete_key(key_name: str) -> JSONResponse:
    """Elimina una clave guardada."""
    from app.mcp import secrets_store
    return JSONResponse(content={"deleted": secrets_store.delete_key(key_name)})


@router.get("/diagnose")
async def diagnose(request: Request) -> JSONResponse:
    """Diagnóstico de por qué los servidores MCP no conectan.

    La mayoría de fallos tienen una de tres causas: falta el runtime (Node/uv),
    falta una clave de API, o el paquete concreto no se pudo descargar. Este
    endpoint las distingue para no dejar al usuario adivinando.
    """
    import shutil
    import os

    # Mismo PATH ampliado que usa el cliente MCP: las apps empaquetadas
    # arrancan sin el PATH del shell del usuario.
    extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
             os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.cargo/bin"),
             os.path.expanduser("~/.nvm/current/bin"), os.path.expanduser("~/.volta/bin"),
             os.path.expanduser("~/.bun/bin"), "/usr/local/sbin"]
    search_path = os.pathsep.join(
        [p for p in extra if os.path.isdir(p)] + [os.environ.get("PATH", "")])

    runtimes = {}
    for name, tool, install in (
        ("node", "npx", "https://nodejs.org  (o: brew install node)"),
        ("python-uv", "uvx", "https://docs.astral.sh/uv  (o: brew install uv)"),
    ):
        found = shutil.which(tool, path=search_path)
        runtimes[name] = {"tool": tool, "available": bool(found),
                          "path": found or "", "install_hint": install}

    manager = getattr(request.app.state, "mcp_manager", None)
    errors = dict(getattr(manager, "_last_errors", {})) if manager else {}
    connected = []
    if manager:
        summary = manager.get_tools_summary()
        connected = [sid for sid, s in (summary.get("servers", {}) or {}).items()
                     if s.get("connected")]

    return JSONResponse(content={
        "runtimes": runtimes,
        "connected_servers": connected,
        "errors": errors,
        "path_searched": search_path,
    })


@router.post("/install-runtime/{runtime}")
async def install_runtime(runtime: str) -> JSONResponse:
    """Instala un runtime necesario para los conectores MCP ('uv' o 'node')."""
    from app.mcp import runtime_installer as ri
    if runtime not in ("uv", "node"):
        return JSONResponse(status_code=400,
                            content={"error": f"Runtime no soportado: {runtime}"})
    outcome = await ri.install_runtime(runtime)
    return JSONResponse(content={
        "runtime": runtime,
        "installed": outcome["ok"],
        "manual": outcome["manual"],
        "message": outcome["message"],
        "available_now": ri.is_available(runtime),
    })
