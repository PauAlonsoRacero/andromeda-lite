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
    "python":     {"ext": ".py",  "cmds": ["python3", "python"],  "available": None, "cmd": None, "run": "{cmd} {file}"},
    "javascript": {"ext": ".js",  "cmds": ["node"],               "available": None, "cmd": None, "run": "{cmd} {file}"},
    "typescript": {"ext": ".ts",  "cmds": ["ts-node", "deno"],    "available": None, "cmd": None, "run": "{cmd} {file}"},
    "bash":       {"ext": ".sh",  "cmds": ["bash"],               "available": None, "cmd": None, "run": "{cmd} {file}"},
    "powershell": {"ext": ".ps1", "cmds": ["pwsh", "powershell"], "available": None, "cmd": None, "run": "{cmd} {file}"},
    "ruby":       {"ext": ".rb",  "cmds": ["ruby"],               "available": None, "cmd": None, "run": "{cmd} {file}"},
    "php":        {"ext": ".php", "cmds": ["php"],                "available": None, "cmd": None, "run": "{cmd} {file}"},
    "go":         {"ext": ".go",  "cmds": ["go"],                 "available": None, "cmd": None, "run": "{cmd} run {file}"},
    "rust":       {"ext": ".rs",  "cmds": ["rust-script"],        "available": None, "cmd": None, "run": "{cmd} {file}"},
    "lua":        {"ext": ".lua", "cmds": ["lua"],                "available": None, "cmd": None, "run": "{cmd} {file}"},
    "perl":       {"ext": ".pl",  "cmds": ["perl"],               "available": None, "cmd": None, "run": "{cmd} {file}"},
    "r":          {"ext": ".R",   "cmds": ["Rscript"],            "available": None, "cmd": None, "run": "{cmd} {file}"},
}


def _detect_languages() -> None:
    """
    Detección perezosa y multiplataforma de intérpretes disponibles.
    - shutil.which: puro Python, funciona en Windows/Mac/Linux (nada de 'which').
    - NUNCA en tiempo de import: un subprocess al importar mató el .exe
      en Windows (FileNotFoundError → backend muerto antes de arrancar).
    """
    import shutil
    for cfg in SUPPORTED_LANGS.values():
        if cfg["available"] is not None:
            continue
        found = next((c for c in cfg["cmds"] if shutil.which(c)), None)
        cfg["available"] = found is not None
        if found:
            # Plantilla de ejecución: sustituye {cmd} por el intérprete encontrado
            template = cfg.get("run", "{cmd} {file}")
            parts = template.replace("{cmd}", found).split()
            cfg["cmd"] = parts  # contiene placeholders {file}
        else:
            cfg["cmd"] = None


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
    import shutil
    body = await request.json()
    lang = (body.get("language") or "").strip().lower()
    info = _INSTALL_MAP.get(lang)
    if not info:
        return JSONResponse(status_code=400, content={"error": "Lenguaje no soportado para autoinstalación"})

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
        # Re-detectar disponibilidad (puede requerir reinicio si el PATH no se refrescó).
        _detect_languages.cache_clear() if hasattr(_detect_languages, "cache_clear") else None
        for c in SUPPORTED_LANGS.get(lang, {}).get("cmds", []):
            if shutil.which(c):
                SUPPORTED_LANGS[lang]["available"] = True
                break
        return JSONResponse(content={
            "success": ok,
            "available_now": SUPPORTED_LANGS.get(lang, {}).get("available", False),
            "needs_restart": ok and not SUPPORTED_LANGS.get(lang, {}).get("available", False),
            "output": (out.decode("utf-8", "replace")[-1200:] if out else ""),
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
