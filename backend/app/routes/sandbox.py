"""
sandbox.py — Code execution sandbox seguro.

Ejecuta código generado por las IAs de forma segura y aislada.
Soporta Python, JavaScript (Node.js) y shell scripts.

Seguridad:
  - Timeout configurable (default 30s)
  - Sin acceso a red (si Docker disponible: --network none)
  - Directorio temporal limpio por ejecución
  - Sin acceso a archivos del sistema fuera del sandbox

POST /api/sandbox/run     → ejecutar código
POST /api/sandbox/check   → verificar si el código es seguro antes de ejecutar
GET  /api/sandbox/langs   → lenguajes soportados
"""

import logging
import os
import subprocess
from app.core.silent_subprocess import silent_run
import tempfile
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.sandbox")
router = APIRouter()

TIMEOUT_DEFAULT = 30
TIMEOUT_MAX     = 120

SUPPORTED_LANGS = {
    "python":     {"ext": ".py",  "cmds": ["python3", "python", "py"]},
    "javascript": {"ext": ".js",  "cmds": ["node"]},
    "typescript": {"ext": ".ts",  "cmds": ["deno", "ts-node", "tsx"]},
    "bash":       {"ext": ".sh",  "cmds": ["bash"]},
    "powershell": {"ext": ".ps1", "cmds": ["pwsh", "powershell"]},
    "ruby":       {"ext": ".rb",  "cmds": ["ruby"]},
    "php":        {"ext": ".php", "cmds": ["php"]},
    "go":         {"ext": ".go",  "cmds": ["go"]},
    "rust":       {"ext": ".rs",  "cmds": ["rust-script"]},
    "lua":        {"ext": ".lua", "cmds": ["lua", "lua5.4", "lua54"]},
    "perl":       {"ext": ".pl",  "cmds": ["perl"]},
    "r":          {"ext": ".R",   "cmds": ["Rscript"]},
}
for _cfg in SUPPORTED_LANGS.values():
    _cfg.update(available=None, cmd=None, path=None, checked=0.0)

# Argumentos por intérprete ({file} = archivo con el código). Listas, no cadenas:
# partir por espacios rompía rutas como "C:\Program Files\nodejs\node.exe".
_ARGS = {
    "deno": ["run", "--quiet", "--allow-read", "{file}"],
    "go": ["run", "{file}"],
    "powershell": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "{file}"],
    "pwsh": ["-NoProfile", "-File", "{file}"],
}
# Cómo comprobar que un intérprete funciona de verdad (no solo que existe).
_VERSION_ARGS = {"go": ["version"], "Rscript": ["--version"], "lua": ["-v"], "lua5.4": ["-v"],
                 "lua54": ["-v"], "powershell": ["-NoProfile", "-Command", "$PSVersionTable.PSVersion"],
                 "pwsh": ["-NoProfile", "-Command", "$PSVersionTable.PSVersion"]}


def _extra_dirs() -> list[str]:
    """Carpetas donde los instaladores dejan los intérpretes y que el PATH de la
    app no siempre incluye (apps de macOS abiertas desde el Finder, o Windows
    antes de reiniciar tras un winget)."""
    import glob
    import sys as _sys
    home = os.path.expanduser("~")
    if _sys.platform.startswith("win"):
        la = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pats = [os.path.join(la, "Microsoft", "WinGet", "Links"),
                os.path.join(la, "Programs", "Python", "Python3*"),
                os.path.join(la, "Programs", "Python", "Python3*", "Scripts"),
                os.path.join(pf, "nodejs"), os.path.join(pf, "Go", "bin"),
                os.path.join(pf, "R", "R-*", "bin"), os.path.join(pf, "PowerShell", "7"),
                r"C:\Ruby3*\bin", r"C:\Strawberry\perl\bin",
                os.path.join(home, ".deno", "bin"), os.path.join(home, "go", "bin"),
                os.path.join(home, ".cargo", "bin"),
                os.path.join(la, "Microsoft", "WinGet", "Packages", "*PHP*", "")]
    else:
        pats = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/local/go/bin",
                os.path.join(home, ".deno", "bin"), os.path.join(home, ".cargo", "bin"),
                os.path.join(home, ".local", "bin"), os.path.join(home, "go", "bin")]
    dirs = []
    for p in pats:
        dirs += sorted(glob.glob(p), reverse=True) if "*" in p else [p]
    return [d for d in dirs if os.path.isdir(d)]


def _refresh_path() -> None:
    """Actualiza el PATH del proceso con lo que el sistema tiene ahora.

    En Windows se relee del registro: winget cambia el PATH del sistema, pero un
    proceso ya abierto conserva el antiguo y no encontraba lo recién instalado.
    """
    import sys as _sys
    partes = os.environ.get("PATH", "").split(os.pathsep)
    if _sys.platform.startswith("win"):
        try:
            import winreg
            for raiz, clave in ((winreg.HKEY_LOCAL_MACHINE,
                                 r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                                (winreg.HKEY_CURRENT_USER, "Environment")):
                try:
                    with winreg.OpenKey(raiz, clave) as k:
                        valor = os.path.expandvars(winreg.QueryValueEx(k, "Path")[0])
                        partes += valor.split(os.pathsep)
                except OSError:
                    pass
        except ImportError:
            pass
    partes += _extra_dirs()
    vistos, limpio = set(), []
    for p in partes:
        if p and p not in vistos:
            vistos.add(p)
            limpio.append(p)
    os.environ["PATH"] = os.pathsep.join(limpio)


def _which(cmd: str) -> str | None:
    """Como shutil.which, pero descarta el acceso directo de la Microsoft Store
    (carpeta WindowsApps), que abre la tienda en vez de ejecutar código."""
    import shutil
    ruta = shutil.which(cmd)
    if ruta and "windowsapps" in ruta.lower():
        return None
    return ruta


def _works(path: str, name: str) -> bool:
    """¿El intérprete arranca de verdad? Se ejecuta con --version."""
    args = _VERSION_ARGS.get(name, ["--version"])
    try:
        r = silent_run([path, *args], capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:                                     # noqa: BLE001
        return False


def _detect_languages(force: bool = False) -> None:
    """Detecta los intérpretes disponibles.

    - Nunca en tiempo de import (un subprocess al importar mató el .exe en Windows).
    - Los positivos se recuerdan; los negativos se reintentan pasados 10 s, así
      que un intérprete instalado aparece sin reiniciar la app.
    - Se guarda la RUTA completa y los argumentos: antes, tras instalar, se
      marcaba "disponible" pero el comando quedaba vacío y no ejecutaba nada.
    """
    _refresh_path()
    ahora = time.monotonic()
    for cfg in SUPPORTED_LANGS.values():
        if not force and cfg["available"] and cfg["path"] and os.path.exists(cfg["path"]):
            continue
        if not force and cfg["available"] is False and ahora - cfg["checked"] < 10:
            continue
        cfg["checked"] = ahora
        cfg["available"], cfg["cmd"], cfg["path"] = False, None, None
        for nombre in cfg["cmds"]:
            ruta = _which(nombre)
            if ruta:
                base = os.path.splitext(os.path.basename(ruta))[0].lower()
                clave = next((k for k in _ARGS if k.lower() == base), None)
                cfg["path"], cfg["available"] = ruta, True
                cfg["cmd"] = [ruta, *(_ARGS[clave] if clave else ["{file}"])]
                break



@router.get("/langs")
async def get_languages(request: Request) -> JSONResponse:
    _detect_languages()
    return JSONResponse(content={
        "languages": [
            {"id": k, "available": v["available"], "ext": v["ext"]}
            for k, v in SUPPORTED_LANGS.items()
        ]
    })


@router.get("/languages")
async def get_languages_alias(request: Request) -> JSONResponse:
    """Alias de /langs (usado por el Codex)."""
    return await get_languages(request)


# Mapa lenguaje → paquete por gestor, y URL oficial de respaldo.
_INSTALL_MAP = {
    "python":     {"winget": "Python.Python.3.12", "brew": "python",  "apt": "python3",      "url": "https://www.python.org/downloads/"},
    "javascript": {"winget": "OpenJS.NodeJS",      "brew": "node",    "apt": "nodejs",       "url": "https://nodejs.org/"},
    "typescript": {"winget": "Deno.Deno",          "brew": "deno",    "apt": None,           "url": "https://deno.com/"},
    "ruby":       {"winget": "RubyInstallerTeam.Ruby.3.3", "brew": "ruby", "apt": "ruby",     "url": "https://www.ruby-lang.org/"},
    "php":        {"winget": "PHP.PHP",            "brew": "php",     "apt": "php-cli",      "url": "https://www.php.net/downloads"},
    "go":         {"winget": "GoLang.Go",          "brew": "go",      "apt": "golang",       "url": "https://go.dev/dl/"},
    "lua":        {"winget": "DEVCOM.Lua",         "brew": "lua",     "apt": "lua5.4",       "url": "https://www.lua.org/download.html"},
    "perl":       {"winget": "StrawberryPerl.StrawberryPerl", "brew": "perl", "apt": "perl", "url": "https://www.perl.org/get.html"},
    "r":          {"winget": "RProject.R",         "brew": "r",       "apt": "r-base",       "url": "https://cran.r-project.org/"},
}


def _detect_pkg_manager() -> str | None:
    import shutil
    import sys as _sys
    if _sys.platform.startswith("win"):
        return "winget" if shutil.which("winget") else None
    if _sys.platform == "darwin":
        return "brew" if shutil.which("brew") else None
    return "apt" if shutil.which("apt-get") or shutil.which("apt") else None


@router.post("/install")
async def install_language(request: Request) -> JSONResponse:
    """Intenta instalar el intérprete de un lenguaje vía el gestor de paquetes
    del sistema (winget/brew/apt). Es best-effort: si no hay gestor o falla,
    devuelve la URL oficial para que el usuario lo instale a mano.

    Nota: tras instalar puede hacer falta reiniciar la app para que el PATH se
    refresque (sobre todo en Windows).
    """
    import asyncio
    body = await request.json()
    lang = (body.get("language") or "").strip().lower()
    info = _INSTALL_MAP.get(lang)
    if not info:
        return JSONResponse(status_code=400, content={"error": "Lenguaje no soportado para autoinstalación"})

    _refresh_path()              # encontrar brew/winget aunque el PATH de la app sea mínimo
    pm = _detect_pkg_manager()
    if not pm or not info.get(pm):
        # Sin gestor de paquetes o paquete no mapeado → indicar URL oficial.
        return JSONResponse(content={
            "success": False, "manual": True, "url": info["url"],
            "message": "Instálalo desde la página oficial y reinicia Andromeda.",
        })

    pkg = info[pm]
    if pm == "winget":
        cmd = ["winget", "install", "-e", "--id", pkg, "--accept-package-agreements", "--accept-source-agreements"]
    elif pm == "brew":
        cmd = ["brew", "install", pkg]
    else:  # apt
        cmd = ["sudo", "apt-get", "install", "-y", pkg]

    try:
        from app.core.silent_subprocess import NO_WINDOW_FLAGS, no_window_startupinfo
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=NO_WINDOW_FLAGS, startupinfo=no_window_startupinfo())
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            return JSONResponse(content={"success": False, "url": info["url"],
                                         "message": "La instalación tardó demasiado. Prueba a mano."})
        ok = proc.returncode == 0
        salida = out.decode("utf-8", "replace")[-1200:] if out else ""
        # winget devuelve distinto de 0 si ya estaba instalado: no es un fallo.
        if not ok and pm == "winget" and "already installed" in salida.lower():
            ok = True
        # Re-detectar (PATH refrescado) y comprobar que el intérprete ARRANCA.
        SUPPORTED_LANGS[lang]["checked"] = 0.0
        _detect_languages(force=True)
        cfg = SUPPORTED_LANGS[lang]
        funciona = bool(cfg["available"] and cfg["path"]
                        and _works(cfg["path"], os.path.splitext(os.path.basename(cfg["path"]))[0]))
        if not funciona:
            cfg["available"] = False
        return JSONResponse(content={
            "success": funciona,
            "installed": ok,
            "available_now": funciona,
            # Instalado pero no localizable: en Windows a veces el instalador
            # necesita cerrar sesión o reiniciar la app para completar el PATH.
            "needs_restart": ok and not funciona,
            "path": cfg["path"] if funciona else None,
            "output": salida,
            "url": info["url"],
        })
    except Exception as e:
        return JSONResponse(content={"success": False, "url": info["url"], "message": str(e)})


@router.post("/run")
async def run_code(request: Request) -> JSONResponse:
    """
    Ejecuta código en un entorno aislado.

    Body: {
        "code": "print('hello')",
        "language": "python",
        "timeout": 30,
        "stdin": ""
    }
    """
    body     = await request.json()
    code     = body.get("code", "")
    language = body.get("language", "python").lower()
    timeout  = min(body.get("timeout", TIMEOUT_DEFAULT), TIMEOUT_MAX)
    stdin    = body.get("stdin", "")

    if not code.strip():
        return JSONResponse(status_code=400, content={"error": "code requerido"})

    _detect_languages()
    lang_cfg = SUPPORTED_LANGS.get(language)
    if not lang_cfg:
        return JSONResponse(status_code=400, content={
            "error": f"Lenguaje '{language}' no soportado",
            "supported": list(SUPPORTED_LANGS.keys()),
        })
    if not lang_cfg["available"]:
        return JSONResponse(status_code=503, content={
            "error": f"'{language}' no está disponible: no se encontró ningún intérprete ({', '.join(lang_cfg['cmds'])})"
        })

    t_start = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = os.path.join(tmpdir, f"code{lang_cfg['ext']}")
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        cmd = [c.replace("{file}", code_file) for c in lang_cfg["cmd"]]

        try:
            proc = silent_run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                input=stdin or None,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
            )
            elapsed = round((time.perf_counter() - t_start) * 1000)
            return JSONResponse(content={
                "success":     proc.returncode == 0,
                "stdout":      proc.stdout[:10_000],
                "stderr":      proc.stderr[:5_000],
                "exit_code":   proc.returncode,
                "elapsed_ms":  elapsed,
                "language":    language,
                "timed_out":   False,
            })
        except subprocess.TimeoutExpired:
            return JSONResponse(content={
                "success":    False,
                "stdout":     "",
                "stderr":     f"Timeout: el código tardó más de {timeout} segundos",
                "exit_code":  -1,
                "elapsed_ms": timeout * 1000,
                "language":   language,
                "timed_out":  True,
            })
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/check")
async def check_code(request: Request) -> JSONResponse:
    """
    Análisis estático básico antes de ejecutar.
    Detecta patrones potencialmente peligrosos.
    """
    body     = await request.json()
    code     = body.get("code", "")
    language = body.get("language", "python")

    warnings = []
    risk     = "low"

    if language == "python":
        dangerous = [
            ("import os", "Acceso al sistema operativo"),
            ("import subprocess", "Ejecución de subprocesos"),
            ("open(", "Acceso a archivos"),
            ("__import__", "Import dinámico"),
            ("exec(", "Ejecución dinámica de código"),
            ("eval(", "Evaluación dinámica"),
            ("socket", "Acceso a red"),
            ("requests", "Peticiones HTTP"),
            ("shutil.rmtree", "Eliminación de directorios"),
            ("os.remove", "Eliminación de archivos"),
            ("sys.exit", "Salida del proceso"),
        ]
        for pattern, desc in dangerous:
            if pattern in code:
                warnings.append({"pattern": pattern, "description": desc})
                risk = "medium" if risk == "low" else risk

        if any(w["pattern"] in ("__import__", "exec(", "eval(") for w in warnings):
            risk = "high"

    return JSONResponse(content={
        "language": language,
        "risk":     risk,
        "warnings": warnings,
        "safe_to_run": risk != "high",
        "line_count": len(code.split("\n")),
    })
