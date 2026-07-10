"""
manager.py — Gestor central de servidores MCP de Andromeda.

Gestiona múltiples servidores MCP simultáneamente.
Lee la configuración de config/mcp_servers.yaml.
Expone todas las herramientas unificadas al orquestador.

Servidores incluidos por defecto:
  filesystem  — leer/escribir/listar archivos locales
  shell       — ejecutar comandos en la terminal
  github      — interactuar con repositorios GitHub
  browser     — control básico del navegador (via playwright)
  database    — consultas a SQLite/PostgreSQL
"""

import asyncio
import logging
import os
from pathlib import Path

import yaml

from app.mcp.protocol import MCPStdioClient, MCPTool, MCPResult

logger = logging.getLogger("andromeda.mcp.manager")


class MCPManager:
    """
    Gestor central de todos los servidores MCP.
    Se inicializa al arrancar Andromeda y mantiene los clientes conectados.
    """

    def __init__(self, config_path: str = "config/mcp_servers.yaml"):
        self._clients:  dict[str, MCPStdioClient] = {}
        self._config_path = config_path
        self._all_tools:  list[MCPTool] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Conecta todos los servidores MCP habilitados en la configuración."""
        config = self._load_config()
        servers = config.get("servers", {})

        tasks = []
        for server_id, server_cfg in servers.items():
            if not server_cfg.get("enabled", False):
                logger.debug(f"MCP [{server_id}] deshabilitado — skip")
                continue
            tasks.append(self._connect_server(server_id, server_cfg))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            connected = sum(1 for r in results if r is True)
            logger.info(f"MCP Manager: {connected}/{len(tasks)} servidores conectados")

        # Consolidar todas las herramientas
        self._all_tools = []
        for client in self._clients.values():
            self._all_tools.extend(client.tools)
        # Herramientas nativas (sin Node): crear/leer/listar archivos. Siempre
        # disponibles, para que el chat pueda crear archivos de fábrica.
        try:
            from app.mcp.builtin_tools import builtin_tools
            self._all_tools.extend(builtin_tools())
        except Exception as exc:
            logger.warning(f"No se pudieron cargar herramientas nativas: {exc}")

        self._initialized = True
        logger.info(f"MCP Manager listo: {len(self._all_tools)} herramientas disponibles")

    def _rebuild_tools(self) -> None:
        """Recalcula la lista consolidada de herramientas tras cambios."""
        self._all_tools = []
        for client in self._clients.values():
            self._all_tools.extend(client.tools)
        try:
            from app.mcp.builtin_tools import builtin_tools
            self._all_tools.extend(builtin_tools())
        except Exception:
            pass

    async def connect_one(self, server_id: str) -> dict:
        """Conecta (o reconecta) un único servidor por id, leyendo su config
        fresca del YAML. Devuelve {connected, tools, count, error?, needs_key?}."""
        import os as _os
        config = self._load_config()
        cfg = (config.get("servers", {}) or {}).get(server_id)
        if cfg is None:
            return {"connected": False, "error": f"Servidor '{server_id}' no existe"}

        # ¿Faltan claves de entorno requeridas? Mensaje claro y accionable.
        required = cfg.get("requires_key", []) or []
        missing = [k for k in required if not _os.environ.get(k)]
        if missing:
            return {
                "connected": False,
                "tools": [], "count": 0,
                "needs_key": missing,
                "error": (f"Este servidor necesita configurar: {', '.join(missing)}. "
                          f"Añádela en Configuración › MCP Tools › {server_id} y vuelve a activar."),
            }

        # Si ya estaba conectado, lo cerramos antes para reconectar limpio
        old = self._clients.pop(server_id, None)
        if old is not None:
            try:
                await old.disconnect()
            except Exception:
                pass
        try:
            ok = await self._connect_server(server_id, cfg)
        except FileNotFoundError:
            self._rebuild_tools()
            runtime = cfg.get("runtime", "node")
            tool = "Node.js (npx)" if runtime == "node" else "uv (uvx)"
            return {"connected": False, "tools": [], "count": 0,
                    "error": f"Falta {tool} en el sistema. Instálalo para usar este servidor."}
        except Exception as exc:
            self._rebuild_tools()
            return {"connected": False, "error": str(exc)}
        self._rebuild_tools()
        client = self._clients.get(server_id)
        return {
            "connected": bool(ok),
            "tools": [t.name for t in client.tools] if client else [],
            "count": len(client.tools) if client else 0,
            "error": None if ok else "No se pudo conectar. Revisa que el runtime esté instalado.",
        }

    async def disconnect_one(self, server_id: str) -> dict:
        """Desconecta y olvida un único servidor por id."""
        client = self._clients.pop(server_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        self._rebuild_tools()
        return {"connected": False, "server_id": server_id}

    async def _connect_server(self, server_id: str, cfg: dict) -> bool:
        raw_command = cfg.get("command", [])
        env         = cfg.get("env", {})
        # Expandir variables de entorno tanto en los argumentos del comando
        # como en el env del servidor (p.ej. ${ANDROMEDA_WORKSPACE}, ${BRAVE_API_KEY})
        command = [os.path.expandvars(str(part)) for part in raw_command]
        expanded_env = {k: os.path.expandvars(str(v)) for k, v in env.items()}

        # Avisar si faltan claves requeridas (no abortamos: algunos toleran su ausencia)
        missing = [k for k in cfg.get("requires_key", []) if not os.environ.get(k)]
        if missing:
            logger.warning(
                f"MCP [{server_id}] requiere variable(s) de entorno sin definir: {missing}. "
                f"El servidor puede fallar al conectar."
            )

        client = MCPStdioClient(server_id=server_id, command=command, env=expanded_env)
        ok = await client.connect()
        if ok:
            self._clients[server_id] = client
            logger.info(f"MCP [{server_id}] conectado — {len(client.tools)} herramientas")
        else:
            logger.warning(f"MCP [{server_id}] no disponible (¿servidor instalado / clave configurada?)")
        return ok

    async def call_tool(self, tool_name: str, arguments: dict, server_id: str | None = None,
                         timeout_s: float = 30.0) -> MCPResult:
        """
        Llama a una herramienta MCP con timeout (por defecto 30s).
        Si server_id es None, busca automáticamente en qué servidor está la herramienta.
        """
        try:
            return await asyncio.wait_for(
                self._call_tool_impl(tool_name, arguments, server_id),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(f"MCP herramienta '{tool_name}' superó {timeout_s}s — cancelada")
            return MCPResult(
                tool_name=tool_name, server_id=server_id or "unknown",
                content=[], is_error=True,
                error_msg=f"La herramienta '{tool_name}' tardó más de {timeout_s:.0f}s y se canceló.",
            )

    async def _call_tool_impl(self, tool_name: str, arguments: dict, server_id: str | None = None) -> MCPResult:
        if server_id is None:
            # Buscar el servidor que tiene esta herramienta
            for tool in self._all_tools:
                if tool.name == tool_name:
                    server_id = tool.server_id
                    break

        # Herramientas nativas de Andromeda (sin proceso externo)
        if server_id == "builtin-fs":
            from app.mcp.builtin_tools import call_builtin
            return await call_builtin(tool_name, arguments)

        if server_id is None or server_id not in self._clients:
            return MCPResult(
                tool_name=tool_name, server_id=server_id or "unknown",
                content=[], is_error=True,
                error_msg=f"Herramienta '{tool_name}' no encontrada en ningún servidor MCP"
            )

        return await self._clients[server_id].call_tool(tool_name, arguments)

    @property
    def tools(self) -> list[MCPTool]:
        return self._all_tools

    @property
    def tools_for_llm(self) -> list[dict]:
        """Formato de herramientas compatible con el schema de Ollama/OpenAI."""
        return [
            {
                "type":     "function",
                "function": {
                    "name":        t.name,
                    "description": t.description,
                    "parameters":  t.input_schema,
                },
            }
            for t in self._all_tools
        ]

    def get_tools_summary(self) -> dict:
        """Resumen para el endpoint /api/mcp/status."""
        summary = {}
        for server_id, client in self._clients.items():
            summary[server_id] = {
                "connected": client.connected,
                "tools":     [t.name for t in client.tools],
                "count":     len(client.tools),
            }
        return {
            "total_tools":   len(self._all_tools),
            "total_servers": len(self._clients),
            "servers":       summary,
        }

    async def shutdown(self):
        """Desconecta todos los servidores."""
        tasks = [c.disconnect() for c in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _load_config(self) -> dict:
        path = Path(self._config_path)
        if not path.exists():
            logger.warning("config/mcp_servers.yaml no encontrado — MCP deshabilitado")
            return {"servers": {}}
        try:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {"servers": {}}
        except Exception as exc:
            logger.error(f"Error leyendo mcp_servers.yaml: {exc}")
            return {"servers": {}}
