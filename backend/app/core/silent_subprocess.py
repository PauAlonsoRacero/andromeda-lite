"""
silent_subprocess.py — subprocess sin ventanas fantasma en Windows.

En un .exe sin consola (PyInstaller console=False), CUALQUIER subprocess abre un
cmd visible un instante. La forma más fiable de evitarlo en Windows es combinar
DOS mecanismos:
  1. creationflags = CREATE_NO_WINDOW
  2. STARTUPINFO con STARTF_USESHOWWINDOW + wShowWindow = SW_HIDE
Algunos ejecutables (p. ej. ollama, npx.cmd) ignoran uno u otro, así que usamos
ambos a la vez. En Linux/Mac no existen y se ignoran.
"""
import subprocess
import sys

_IS_WIN = sys.platform == "win32"
_FLAGS = subprocess.CREATE_NO_WINDOW if _IS_WIN else 0
# Exportado para los subprocess ASÍNCRONOS (asyncio.create_subprocess_*).
NO_WINDOW_FLAGS = _FLAGS


def _startupinfo():
    """STARTUPINFO que oculta la ventana (Windows). None en otros SO."""
    if not _IS_WIN:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE  # 0 = SW_HIDE
    return si


# Alias para los spawns asíncronos que aceptan startupinfo.
def no_window_startupinfo():
    return _startupinfo()


def silent_run(*args, **kwargs):
    """Igual que subprocess.run pero sin abrir ventana de consola en Windows."""
    kwargs.setdefault("creationflags", _FLAGS)
    if _IS_WIN:
        kwargs.setdefault("startupinfo", _startupinfo())
    return subprocess.run(*args, **kwargs)
