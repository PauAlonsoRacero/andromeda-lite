"""
runtime_installer.py — Instalación automática de los runtimes que MCP necesita.

Andromeda promete ser plug and play, pero los servidores MCP dependen de
runtimes externos: `npx` (Node.js) para los servidores en JavaScript y `uvx`
(uv) para los de Python. Si faltan, el usuario ve "sin conectar" y se queda
atascado en instrucciones de terminal, que es justo lo contrario de plug and
play.

Este módulo detecta qué falta y lo instala sin intervención cuando es posible:

  • uv: instalador oficial de Astral, sin permisos de administrador. Se
    descarga a ~/.local/bin. Es rápido (unos segundos) y seguro de automatizar.
  • Node: NO se automatiza. Instalarlo requiere privilegios de administrador o
    Homebrew, y hacerlo a espaldas del usuario sería intrusivo. En su lugar se
    devuelve una instrucción concreta y copiable.

Esa asimetría es deliberada: automatizamos lo que es reversible y contenido en
el directorio del usuario, y pedimos permiso para lo que toca el sistema.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys

logger = logging.getLogger("andromeda.mcp.installer")

# Mismo PATH ampliado que usa el cliente MCP: una app empaquetada arranca sin
# el PATH del shell del usuario y no ve Homebrew ni ~/.local/bin.
_EXTRA_PATHS = [
    "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.cargo/bin"),
    os.path.expanduser("~/.nvm/current/bin"),
    os.path.expanduser("~/.volta/bin"),
    os.path.expanduser("~/.bun/bin"),
    "/usr/local/sbin",
]


def search_path() -> str:
    """PATH ampliado para buscar y ejecutar herramientas externas."""
    return os.pathsep.join(
        [p for p in _EXTRA_PATHS if os.path.isdir(p)] + [os.environ.get("PATH", "")]
    )


def ensure_path_in_environ() -> None:
    """Añade las rutas habituales al PATH del proceso.

    Sin esto, una herramienta recién instalada en ~/.local/bin no se encuentra
    hasta reiniciar la app.
    """
    os.environ["PATH"] = search_path()


def which(tool: str) -> str | None:
    return shutil.which(tool, path=search_path())


def runtime_for_command(command: list[str]) -> str | None:
    """Qué runtime necesita un comando de servidor MCP: 'node', 'uv' o None."""
    if not command:
        return None
    exe = os.path.basename(str(command[0])).lower()
    if exe.startswith("npx"):
        return "node"
    if exe.startswith("uvx") or exe.startswith("uv"):
        return "uv"
    return None


def is_available(runtime: str) -> bool:
    """True si el runtime está instalado y accesible."""
    if runtime == "node":
        return which("npx") is not None
    if runtime == "uv":
        return which("uvx") is not None
    return False        # runtime desconocido: nunca "disponible"


async def _run(cmd: list[str], timeout: float = 240.0) -> tuple[bool, str]:
    """Ejecuta un comando y devuelve (éxito, salida combinada)."""
    try:
        # PyInstaller inyecta variables (_MEIPASS, LD_LIBRARY_PATH…) que apuntan
        # a las librerías embebidas del bundle. Si se heredan, los procesos hijo
        # cargan las librerías equivocadas o se comportan de forma extraña.
        env = {k: v for k, v in os.environ.items()
               if k not in ("_MEIPASS", "_MEIPASS2", "LD_LIBRARY_PATH",
                            "DYLD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")}
        env["PATH"] = search_path()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        text = (out or b"").decode("utf-8", "replace").strip()
        return proc.returncode == 0, text[-800:]
    except asyncio.TimeoutError:
        return False, "La instalación tardó demasiado y se canceló."
    except FileNotFoundError:
        return False, f"No se encontró el comando: {cmd[0]}"
    except Exception as exc:                              # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _real_python() -> str | None:
    """Ruta a un intérprete de Python de verdad, o None si no hay ninguno.

    CRÍTICO en apps empaquetadas: bajo PyInstaller `sys.executable` apunta al
    binario de Andromeda, no a Python. Llamarlo con `-m pip` no instala nada:
    ARRANCA OTRA COPIA DE LA APLICACIÓN. Por eso aquí se busca un Python del
    sistema y se descarta explícitamente el ejecutable congelado.
    """
    frozen = getattr(sys, "frozen", False)
    if not frozen:
        return sys.executable
    for name in ("python3", "python"):
        found = which(name)
        # Un python que resuelva al propio bundle no sirve.
        if found and "Andromeda" not in found and "andromeda" not in found:
            return found
    return None


async def install_uv() -> tuple[bool, str]:
    """Instala uv (que provee uvx) en el directorio del usuario.

    Se prueba primero con pip, que es la vía más predecible y no depende de
    redes de terceros. Si no hay un Python utilizable o falla, se recurre al
    instalador oficial.
    """
    py = _real_python()
    if py:
        ok, out = await _run([py, "-m", "pip", "install", "--user", "-q", "uv"], 180)
        if ok and which("uvx"):
            ensure_path_in_environ()
            return True, "uv instalado correctamente."
    out = ""

    if sys.platform == "win32":
        ok, out = await _run(
            ["powershell", "-NoProfile", "-Command",
             "irm https://astral.sh/uv/install.ps1 | iex"], 240)
    else:
        ok, out = await _run(
            ["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], 240)

    ensure_path_in_environ()
    if which("uvx"):
        return True, "uv instalado correctamente."

    # Si la instalación automática falla (sin red, proxy corporativo, permisos),
    # el error crudo de curl no le dice nada al usuario. Se le da la instrucción
    # concreta para hacerlo él.
    if sys.platform == "darwin":
        manual = "brew install uv"
    elif sys.platform == "win32":
        manual = "winget install astral-sh.uv"
    else:
        manual = "pip install --user uv"
    detail = f" (detalle: {out.splitlines()[-1][:120]})" if out else ""
    return False, (f"No se pudo instalar uv automáticamente{detail}. "
                   f"Puedes instalarlo tú con:\n    {manual}")


async def install_runtime(runtime: str) -> dict:
    """Instala un runtime si es posible.

    Returns:
        {"ok": bool, "message": str, "manual": bool}
        `manual=True` significa que el usuario debe instalarlo él mismo y el
        mensaje contiene la instrucción exacta.
    """
    if is_available(runtime):
        return {"ok": True, "message": "Ya estaba disponible.", "manual": False}

    if runtime == "uv":
        ok, msg = await install_uv()
        return {"ok": ok, "message": msg, "manual": False}

    if runtime == "node":
        # Node requiere privilegios de administrador o un gestor de paquetes:
        # instalarlo automáticamente sería intrusivo y frágil.
        if sys.platform == "darwin":
            hint = ("Node.js hace falta para este conector. Instálalo con:\n"
                    "    brew install node\n"
                    "o descárgalo de https://nodejs.org")
        elif sys.platform == "win32":
            hint = ("Node.js hace falta para este conector. Instálalo con:\n"
                    "    winget install OpenJS.NodeJS\n"
                    "o descárgalo de https://nodejs.org")
        else:
            hint = ("Node.js hace falta para este conector. Instálalo con el gestor "
                    "de paquetes de tu sistema, p. ej.:\n"
                    "    sudo apt install nodejs npm")
        return {"ok": False, "message": hint, "manual": True}

    return {"ok": False, "message": f"Runtime desconocido: {runtime}", "manual": True}
