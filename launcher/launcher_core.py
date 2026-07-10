"""
launcher_core.py — Lógica compartida del launcher de Andromeda.
Detecta el OS, comprueba dependencias, arranca Docker, descarga modelos
y abre el navegador. Diseñado para que TODO funcione a la primera.
"""
import os
import sys
import time
import json
import platform
import subprocess
import urllib.request
import webbrowser

ANDROMEDA_VERSION = "1.0.0"
BACKEND_URL       = "http://localhost:8000/api/health"
FRONTEND_URL      = "http://localhost"
OLLAMA_URL        = "http://localhost:11434"

OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Modelos mínimos para que el sistema funcione out-of-the-box
STARTER_MODELS = [
    ("phi3.5:3.8b",       "Orquestador + Verifier + Summarizer"),
    ("mistral:7b",        "Generalist"),
    ("qwen2.5-coder:7b",  "Software Engineering"),
]

# ── Colores para terminal ─────────────────────────────────────────────────────
def _supports_color():
    if OS == "Windows":
        # Windows 10+ soporta ANSI si se habilita
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True

_COLOR = _supports_color()
def _c(code, text): return f"\033[{code}m{text}\033[0m" if _COLOR else text
def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def red(t):    return _c("31", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)

def ok(msg):   print(f"  {green('OK')} {msg}")
def warn(msg): print(f"  {yellow('!')} {msg}")
def err(msg):  print(f"  {red('X')} {msg}")
def step(n, msg): print(f"\n{cyan(f'[{n}]')} {bold(msg)}")

def banner():
    print()
    print(cyan("  +======================================================+"))
    print(cyan("  |") + bold("   * ANDROMEDA  AI Orchestration Platform           ") + cyan("|"))
    print(cyan("  |") + f"     v{ANDROMEDA_VERSION}  -  Local . Private . Modular           " + cyan("|"))
    print(cyan("  +======================================================+"))
    print()

def get_install_dir():
    """Directorio donde está el ejecutable o el proyecto."""
    if getattr(sys, 'frozen', False):
        # Ejecutable PyInstaller — el .exe está en la raíz del proyecto
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Docker ────────────────────────────────────────────────────────────────────

def is_docker_installed():
    try:
        r = subprocess.run(["docker", "--version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def is_docker_running():
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def start_docker_desktop():
    """Arranca Docker Desktop según el OS. Retorna True si lo intentó."""
    if OS == "Windows":
        paths = [
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                subprocess.Popen([p], shell=False)
                return True
    elif OS == "Darwin":
        if os.path.exists("/Applications/Docker.app"):
            subprocess.Popen(["open", "-a", "Docker"])
            return True
    return False

def wait_for_docker(max_seconds=120):
    """Espera a que Docker esté listo. Retorna True si arrancó."""
    start = time.time()
    while time.time() - start < max_seconds:
        if is_docker_running():
            return True
        time.sleep(3)
    return False

# ── Backend ─────────────────────────────────────────────────────────────────

def is_backend_ready():
    try:
        with urllib.request.urlopen(BACKEND_URL, timeout=3) as r:
            return r.status in (200, 503)
    except Exception:
        return False

def wait_for_backend(max_seconds=180):
    start = time.time()
    while time.time() - start < max_seconds:
        if is_backend_ready():
            return True
        time.sleep(2)
    return False

def get_backend_status():
    """Devuelve el JSON de /api/health o None."""
    try:
        with urllib.request.urlopen(BACKEND_URL, timeout=3) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

# ── Docker Compose ────────────────────────────────────────────────────────────

def run_docker_compose(install_dir, action="up", build=False):
    """Ejecuta docker-compose. Soporta 'docker compose' (v2) y 'docker-compose' (v1)."""
    # Detectar qué comando está disponible
    compose_cmd = _detect_compose_cmd()
    cmd = list(compose_cmd)
    if action == "up":
        cmd += ["up", "-d"]
        if build:
            cmd += ["--build"]
    elif action == "down":
        cmd += ["down"]
    elif action == "restart":
        cmd += ["restart"]

    result = subprocess.run(cmd, cwd=install_dir, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

def _detect_compose_cmd():
    """Detecta si usar 'docker compose' o 'docker-compose'."""
    try:
        r = subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return ["docker", "compose"]
    except Exception:
        pass
    return ["docker-compose"]

def get_running_containers():
    """Lista de contenedores de Andromeda corriendo."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=andromeda", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10
        )
        return [c for c in r.stdout.strip().split("\n") if c]
    except Exception:
        return []

# ── Ollama / Modelos ──────────────────────────────────────────────────────────

def get_installed_models():
    """Lista de modelos ya descargados en Ollama."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []

def pull_model(model_name, on_progress=None):
    """Descarga un modelo vía docker exec. Retorna True si tuvo éxito."""
    try:
        proc = subprocess.Popen(
            ["docker", "exec", "andromeda-ollama", "ollama", "pull", model_name],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            if on_progress:
                on_progress(line.strip())
        proc.wait()
        return proc.returncode == 0
    except Exception:
        return False

def missing_starter_models():
    """Devuelve los modelos starter que aún no están descargados."""
    installed = get_installed_models()
    missing = []
    for model, role in STARTER_MODELS:
        if not any(model in inst for inst in installed):
            missing.append((model, role))
    return missing

# ── Navegador ─────────────────────────────────────────────────────────────────

def open_browser():
    time.sleep(1)
    webbrowser.open(FRONTEND_URL)
