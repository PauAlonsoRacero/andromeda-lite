"""
Herramientas integradas (nativas) de Andromeda — sin Node ni npx.

El servidor MCP 'filesystem' oficial necesita Node.js, que mucha gente no tiene.
Para que crear/leer archivos funcione SIEMPRE de fábrica, implementamos esas
herramientas en Python puro y las registramos directamente en el MCPManager.

Seguridad: las operaciones se limitan a un directorio raíz seguro (el escritorio
del usuario o ANDROMEDA_WORKSPACE), nunca a todo el disco.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.mcp.protocol import MCPTool, MCPResult

SERVER_ID = "builtin-fs"


def _root() -> Path:
    """Directorio raíz permitido para operaciones de archivo."""
    env = os.environ.get("ANDROMEDA_WORKSPACE")
    if env:
        p = Path(env).expanduser()
    else:
        # Por defecto, el escritorio del usuario (o home si no existe).
        desktop = Path.home() / "Desktop"
        p = desktop if desktop.exists() else Path.home()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _safe_path(raw: str) -> Path:
    """Resuelve una ruta DENTRO del root permitido (evita escapes con ../).

    Cualquier ruta que, tras resolverse, caiga fuera del root se reancla al root
    usando solo su nombre de archivo. Esto bloquea ../../etc/passwd y similares.
    """
    root = _root().resolve()
    candidate = Path(raw).expanduser()
    # Resolver SIEMPRE contra el root y normalizar (resuelve los ../).
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    # Comprobar que sigue dentro del root; si no, reanclar por seguridad.
    try:
        resolved.relative_to(root)
        return resolved
    except ValueError:
        return root / Path(raw).name  # fuera del root → solo el nombre, dentro


def builtin_tools() -> list[MCPTool]:
    """Devuelve las herramientas nativas (siempre disponibles)."""
    tools = [
        MCPTool(
            name="write_file",
            description="Crea o sobrescribe un archivo de texto con el contenido dado. Úsala para crear .txt, .md, .csv, código, etc.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Nombre o ruta del archivo (p.ej. 'numeros.txt')"},
                    "content": {"type": "string", "description": "Contenido completo del archivo"},
                },
                "required": ["path", "content"],
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="read_file",
            description="Lee y devuelve el contenido de un archivo de texto.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Nombre o ruta del archivo"}},
                "required": ["path"],
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="list_files",
            description="Lista los archivos y carpetas del directorio de trabajo (o de una subcarpeta).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Subcarpeta opcional"}},
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="delete_file",
            description="Borra un archivo (o una carpeta vacía) del directorio de trabajo.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Archivo o carpeta a borrar"}},
                "required": ["path"],
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="append_file",
            description="Añade contenido al final de un archivo existente (lo crea si no existe).",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Archivo a modificar"},
                    "content": {"type": "string", "description": "Texto a añadir al final"},
                },
                "required": ["path", "content"],
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="edit_file",
            description="Modifica un archivo reemplazando un texto por otro (buscar y reemplazar). Útil para editar sin reescribir todo.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Archivo a editar"},
                    "find": {"type": "string", "description": "Texto exacto a buscar"},
                    "replace": {"type": "string", "description": "Texto que lo sustituye"},
                },
                "required": ["path", "find", "replace"],
            },
            server_id=SERVER_ID,
        ),
        MCPTool(
            name="make_dir",
            description="Crea una carpeta (y las intermedias que falten) dentro del directorio de trabajo.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Ruta de la carpeta a crear"}},
                "required": ["path"],
            },
            server_id=SERVER_ID,
        ),
    ]
    # run_command es POTENTE y potencialmente peligrosa: solo se ofrece si el
    # usuario la habilita explícitamente (ANDROMEDA_ALLOW_SHELL=1). Por defecto
    # NO está disponible, para no dar ejecución de comandos sin consentimiento.
    if os.environ.get("ANDROMEDA_ALLOW_SHELL") == "1":
        tools.append(MCPTool(
            name="run_command",
            description="Ejecuta un comando de terminal seguro (lista blanca: ls, cat, echo, pwd, date, whoami, python --version, etc.) en el directorio de trabajo. NO permite comandos destructivos.",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Comando a ejecutar"}},
                "required": ["command"],
            },
            server_id=SERVER_ID,
        ))
    return tools


def _ok(tool, text):
    return MCPResult(tool_name=tool, server_id=SERVER_ID, content=[{"type": "text", "text": text}])

def _err(tool, msg):
    return MCPResult(tool_name=tool, server_id=SERVER_ID, content=[], is_error=True, error_msg=msg)


# Comandos permitidos para run_command (lista blanca de solo lectura/inocuos).
_SAFE_COMMANDS = {
    "ls", "dir", "cat", "type", "echo", "pwd", "cd", "date", "whoami",
    "head", "tail", "wc", "find", "grep", "python", "python3", "node", "pip",
}
# Patrones SIEMPRE prohibidos aunque empiecen por comando seguro.
_FORBIDDEN = ("rm ", "rmdir", "del ", "format", "mkfs", "dd ", ">", ">>", "|",
              "sudo", "chmod", "chown", "curl", "wget", "&&", ";", "`", "$(")


async def call_builtin(tool_name: str, arguments: dict) -> MCPResult:
    """Ejecuta una herramienta nativa. Devuelve MCPResult."""
    try:
        if tool_name == "write_file":
            path = _safe_path(arguments.get("path", "archivo.txt"))
            content = arguments.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return _ok(tool_name, f"Archivo creado: {path} ({len(content)} caracteres)")

        if tool_name == "read_file":
            path = _safe_path(arguments.get("path", ""))
            if not path.exists():
                return _err(tool_name, f"Not found: {path}")
            txt = path.read_text(encoding="utf-8", errors="replace")
            return _ok(tool_name, txt[:10000])

        if tool_name == "list_files":
            base = _safe_path(arguments["path"]) if arguments.get("path") else _root()
            if not base.exists():
                return _err(tool_name, f"Not found: {base}")
            entries = []
            for f in sorted(base.iterdir()):
                entries.append(f"{f.name}/" if f.is_dir() else f.name)
            return _ok(tool_name, "\n".join(entries) or "(vacío)")

        if tool_name == "delete_file":
            path = _safe_path(arguments.get("path", ""))
            if not path.exists():
                return _err(tool_name, f"Not found: {path}")
            if path.is_dir():
                try:
                    path.rmdir()  # solo carpeta vacía, por seguridad
                except OSError:
                    return _err(tool_name, f"La carpeta no está vacía: {path}. Borra antes su contenido.")
            else:
                path.unlink()
            return _ok(tool_name, f"Borrado: {path}")

        if tool_name == "append_file":
            path = _safe_path(arguments.get("path", ""))
            content = arguments.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(content)
            return _ok(tool_name, f"Añadido a {path} ({len(content)} caracteres)")

        if tool_name == "edit_file":
            path = _safe_path(arguments.get("path", ""))
            if not path.exists():
                return _err(tool_name, f"Not found: {path}")
            find = arguments.get("find", "")
            replace = arguments.get("replace", "")
            txt = path.read_text(encoding="utf-8", errors="replace")
            if find not in txt:
                return _err(tool_name, f"No se encontró el texto a reemplazar en {path}")
            n = txt.count(find)
            path.write_text(txt.replace(find, replace), encoding="utf-8")
            return _ok(tool_name, f"Editado {path}: {n} reemplazo(s)")

        if tool_name == "make_dir":
            path = _safe_path(arguments.get("path", ""))
            path.mkdir(parents=True, exist_ok=True)
            return _ok(tool_name, f"Carpeta creada: {path}")

        if tool_name == "run_command":
            if os.environ.get("ANDROMEDA_ALLOW_SHELL") != "1":
                return _err(tool_name, "Ejecución de comandos deshabilitada. Actívala con ANDROMEDA_ALLOW_SHELL=1.")
            cmd = (arguments.get("command") or "").strip()
            if not cmd:
                return _err(tool_name, "Comando vacío.")
            low = cmd.lower()
            if any(bad in low for bad in _FORBIDDEN):
                return _err(tool_name, "Command blocked for safety (destructive or disallowed operation).")
            prog = low.split()[0]
            if prog not in _SAFE_COMMANDS:
                return _err(tool_name, f"Comando '{prog}' no está en la lista blanca. Permitidos: {', '.join(sorted(_SAFE_COMMANDS))}")
            import asyncio
            from app.core.silent_subprocess import NO_WINDOW_FLAGS, no_window_startupinfo
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, cwd=str(_root()),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    creationflags=NO_WINDOW_FLAGS, startupinfo=no_window_startupinfo(),
                )
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                return _ok(tool_name, (out.decode("utf-8", "replace")[:5000]) or "(sin salida)")
            except asyncio.TimeoutError:
                return _err(tool_name, "El comando tardó más de 15s y se canceló.")

    except OSError as exc:
        import errno
        if exc.errno == errno.ENOSPC:
            return _err(tool_name, "No queda espacio en disco. Libera espacio y reintenta.")
        if exc.errno in (errno.EACCES, errno.EPERM):
            return _err(tool_name, "Permiso denegado para esa ruta. Prueba con otra carpeta del workspace.")
        if exc.errno == errno.EROFS:
            return _err(tool_name, "The file system is read-only at that path.")
        return _err(tool_name, f"Error de archivo: {exc.strerror or str(exc)}")
    except Exception as exc:
        return _err(tool_name, str(exc))
    return _err(tool_name, f"Herramienta nativa desconocida: {tool_name}")
