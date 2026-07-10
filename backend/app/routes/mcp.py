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
        return JSONResponse(status_code=503, content={"error": "MCP no disponible"})

    body      = await request.json()
    tool_name = body.get("tool")
    arguments = body.get("arguments", {})
    server_id = body.get("server_id")

    if not tool_name:
        return JSONResponse(status_code=400, content={"error": "Campo 'tool' requerido"})

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
        return JSONResponse(status_code=400, content={"error": "Campo 'prompt' requerido"})

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
        return JSONResponse(status_code=503, content={"error": "MCP no inicializado"})

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
                data = yaml.safe_load(f) or {}
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
                    "docs": cfg.get("docs", ""),
                    "connected": conn.get("connected", False),
                    "tools": conn.get("tools", []),
                    "tool_count": conn.get("count", 0),
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
            data = yaml.safe_load(f) or {}
        if server_id not in (data.get("servers", {}) or {}):
            return JSONResponse(status_code=404, content={
                "error": True, "message": f"Servidor '{server_id}' no existe"
            })
        data["servers"][server_id]["enabled"] = enabled
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # Aplicar AL INSTANTE: al activar, conectamos ese servidor (npx/uvx lo
        # descarga solo la primera vez); al desactivar, lo desconectamos. Sin
        # necesidad de pulsar "Reconectar".
        manager = getattr(request.app.state, 'mcp_manager', None)
        result = {}
        if manager:
            if enabled:
                result = await manager.connect_one(server_id)
            else:
                result = await manager.disconnect_one(server_id)

        ok = result.get("connected", False)
        if enabled and not ok:
            message = result.get("error") or "Activado, pero no se pudo conectar."
        elif enabled:
            message = f"Conectado — {result.get('count', 0)} herramientas."
        else:
            message = "Desactivado."

        return JSONResponse(content={
            "success": True,
            "server_id": server_id,
            "enabled": enabled,
            "connected": ok,
            "tools": result.get("tools", []),
            "tool_count": result.get("count", 0),
            "needs_key": result.get("needs_key", []),
            "message": message,
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={
            "error": True, "message": f"Error: {exc}"
        })
