"""
protocol.py — Implementación del protocolo MCP (Model Context Protocol).

MCP es un protocolo JSON-RPC 2.0 sobre stdio o HTTP/SSE.
Este módulo implementa el cliente MCP que Andromeda usa para
conectarse a servidores MCP externos.

Protocolo MCP:
  Cliente → Servidor: {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
  Servidor → Cliente: {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

  Cliente → Servidor: {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_file","arguments":{"path":"/tmp/x"}}}
  Servidor → Cliente: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"..."}]}}
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("andromeda.mcp.protocol")


@dataclass
class MCPTool:
    """Herramienta disponible en un servidor MCP."""
    name: str
    description: str
    input_schema: dict
    server_id: str

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "description":  self.description,
            "input_schema": self.input_schema,
            "server_id":    self.server_id,
        }


@dataclass
class MCPResult:
    """Resultado de una llamada a una herramienta MCP."""
    tool_name:   str
    server_id:   str
    content:     list[dict]
    is_error:    bool = False
    error_msg:   str  = ""

    @property
    def text(self) -> str:
        """Extrae el texto de los content blocks."""
        parts = []
        for block in self.content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)


class MCPStdioClient:
    """
    Cliente MCP sobre stdio.
    Arranca un servidor MCP como subproceso y se comunica
    con él por stdin/stdout usando JSON-RPC 2.0.
    """

    def __init__(self, server_id: str, command: list[str], env: dict | None = None):
        self.server_id  = server_id
        self.command    = command
        self.env        = env
        self._process:  subprocess.Popen | None = None
        self._tools:    list[MCPTool] = []
        self._req_id    = 0
        self._lock      = asyncio.Lock()
        self._connected = False

    async def connect(self) -> bool:
        """Arranca el servidor MCP y hace el handshake inicial."""
        try:
            import os
            import shutil
            import subprocess as _sp
            import sys as _sys
            env = {**os.environ, **(self.env or {})}

            # Las apps GUI empaquetadas (.app de macOS, .exe) arrancan con un PATH
            # mínimo que NO incluye donde viven npx/uvx (Homebrew, ~/.local/bin, nvm…).
            # Lo ampliamos para que los servidores MCP se encuentren y arranquen.
            extra_paths = [
                "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.cargo/bin"),
                os.path.expanduser("~/.nvm/current/bin"),
                os.path.expanduser("~/.volta/bin"),
                os.path.expanduser("~/.bun/bin"),
                "/usr/local/sbin",
            ]
            cur_path = env.get("PATH", "")
            env["PATH"] = os.pathsep.join(
                [p for p in extra_paths if os.path.isdir(p)] + ([cur_path] if cur_path else [])
            )

            flags = _sp.CREATE_NO_WINDOW if _sys.platform == "win32" else 0
            _si = None
            if _sys.platform == "win32":
                _si = _sp.STARTUPINFO(); _si.dwFlags |= _sp.STARTF_USESHOWWINDOW; _si.wShowWindow = _sp.SW_HIDE
            # En Windows "npx" es "npx.cmd": resolver la ruta real del ejecutable.
            # Usamos el PATH ampliado para localizarlo también en macOS/Linux.
            cmd = list(self.command)
            resolved = shutil.which(cmd[0], path=env["PATH"])
            if resolved:
                cmd[0] = resolved
            else:
                logger.warning(
                    f"MCP [{self.server_id}]: no se encontró '{cmd[0]}' en el PATH. "
                    f"¿Está instalado Node (npx) o uv (uvx)?"
                )
                return False
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin  = asyncio.subprocess.PIPE,
                stdout = asyncio.subprocess.PIPE,
                stderr = asyncio.subprocess.PIPE,
                env    = env,
                creationflags = flags,
                startupinfo = _si,
            )
            # Handshake: initialize
            resp = await self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities":    {"tools": {}},
                "clientInfo":      {"name": "andromeda", "version": "1.0.0"},
            })
            if not resp:
                return False

            # Notificar initialized
            await self._notify("notifications/initialized", {})

            # Listar herramientas disponibles
            tools_resp = await self._request("tools/list", {})
            if tools_resp and "tools" in tools_resp:
                self._tools = [
                    MCPTool(
                        name         = t["name"],
                        description  = t.get("description", ""),
                        input_schema = t.get("inputSchema", {}),
                        server_id    = self.server_id,
                    )
                    for t in tools_resp["tools"]
                ]
                logger.info(f"MCP [{self.server_id}]: {len(self._tools)} herramientas disponibles")

            self._connected = True
            return True

        except Exception as exc:
            logger.error(f"MCP [{self.server_id}] connect error: {exc}")
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> MCPResult:
        """Llama a una herramienta del servidor MCP."""
        if not self._connected:
            return MCPResult(
                tool_name=tool_name, server_id=self.server_id,
                content=[], is_error=True, error_msg="Servidor no conectado"
            )
        try:
            resp = await self._request("tools/call", {
                "name":      tool_name,
                "arguments": arguments,
            })
            if resp is None:
                return MCPResult(tool_name=tool_name, server_id=self.server_id,
                                 content=[], is_error=True, error_msg="Sin respuesta")

            content  = resp.get("content", [])
            is_error = resp.get("isError", False)
            return MCPResult(tool_name=tool_name, server_id=self.server_id,
                             content=content, is_error=is_error)
        except Exception as exc:
            return MCPResult(tool_name=tool_name, server_id=self.server_id,
                             content=[], is_error=True, error_msg=str(exc))

    @property
    def tools(self) -> list[MCPTool]:
        return self._tools

    @property
    def connected(self) -> bool:
        return self._connected

    async def disconnect(self):
        if self._process:
            try: self._process.terminate()
            except (ProcessLookupError, OSError): pass
        self._connected = False

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _request(self, method: str, params: dict) -> dict | None:
        """Envía un request JSON-RPC y espera la respuesta."""
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
            msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

            try:
                self._process.stdin.write((msg + "\n").encode())
                await self._process.stdin.drain()

                # Leer respuesta con timeout
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=30.0
                )
                if not line:
                    return None

                data = json.loads(line.decode().strip())
                if data.get("id") != req_id:
                    return None

                if "error" in data:
                    logger.error(f"MCP error: {data['error']}")
                    return None

                return data.get("result")

            except asyncio.TimeoutError:
                logger.error(f"MCP [{self.server_id}] timeout en {method}")
                return None
            except Exception as exc:
                logger.error(f"MCP [{self.server_id}] request error: {exc}")
                return None

    async def _notify(self, method: str, params: dict):
        """Envía una notificación (sin esperar respuesta)."""
        try:
            msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
            self._process.stdin.write((msg + "\n").encode())
            await self._process.stdin.drain()
        except Exception:
            pass
