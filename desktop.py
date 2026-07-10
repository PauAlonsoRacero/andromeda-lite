r"""
desktop.py — Lanzador de Andromeda como aplicación de escritorio standalone.

Arranca el backend FastAPI en un hilo y abre una ventana NATIVA (pywebview).
Todo el output va a un archivo de log para poder diagnosticar fallos
(crítico: en modo ventana de PyInstaller, sys.stdout/stderr son None y
cualquier print/log a consola crashea el proceso en silencio).

Log:  %APPDATA%\Andromeda\andromeda.log   (Windows)
      ~/Library/Application Support/Andromeda/andromeda.log   (macOS)
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path


# ── Rutas ─────────────────────────────────────────────────────────────────────
def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    d = base / "Andromeda"
    d.mkdir(parents=True, exist_ok=True)
    return d


ROOT = app_root()
DATA_DIR = user_data_dir()
LOG_PATH = DATA_DIR / "andromeda.log"

# ── CRÍTICO: redirigir stdout/stderr ANTES de cualquier import que loguee ────
# En un .exe sin consola (console=False), sys.stdout es None. Uvicorn, logging
# y cualquier print() crashearían el backend al instante.
_log_file = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")
if sys.stdout is None or getattr(sys, "frozen", False):
    sys.stdout = _log_file
if sys.stderr is None or getattr(sys, "frozen", False):
    sys.stderr = _log_file

print(f"\n{'='*60}\nAndromeda Desktop — arranque {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"ROOT={ROOT}\nDATA={DATA_DIR}\nPython={sys.version}\nfrozen={getattr(sys,'frozen',False)}")

BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"
sys.path.insert(0, str(BACKEND))

# Config vía env (prefijo ANDROMEDA_ + nombre exacto del campo de Settings)
os.environ.setdefault("ANDROMEDA_FRONTEND_DIST", str(DIST))
os.environ.setdefault("ANDROMEDA_DATA_DIR", str(DATA_DIR))


# ── i18n del splash (la UI aún no ha cargado, así que traducimos aquí) ──────────
def _detect_lang() -> str:
    """Idioma para el splash: lo guardado por la UI, o el locale del SO, o 'en'."""
    try:
        import json as _json
        st = DATA_DIR / "ui_state.json"
        if st.exists():
            v = _json.loads(st.read_text(encoding="utf-8")).get("andromeda_lang")
            if v in ("en", "es", "de", "zh", "fr"):
                return v
    except Exception:
        pass
    try:
        import locale
        code = (locale.getdefaultlocale()[0] or "en")[:2].lower()
        if code in ("en", "es", "de", "zh", "fr"):
            return code
    except Exception:
        pass
    return "en"


_SPLASH_I18N = {
    "sub":      {"en": "Local AI orchestration", "es": "Orquestaci\u00f3n de IA local",
                 "de": "Lokale KI-Orchestrierung", "zh": "\u672c\u5730 AI \u7f16\u6392", "fr": "Orchestration d'IA locale"},
    "init":     {"en": "Starting core\u2026", "es": "Iniciando n\u00facleo\u2026",
                 "de": "Kern wird gestartet\u2026", "zh": "\u6b63\u5728\u542f\u52a8\u6838\u5fc3\u2026", "fr": "D\u00e9marrage du noyau\u2026"},
    "backend":  {"en": "Starting backend\u2026", "es": "Arrancando backend\u2026",
                 "de": "Backend wird gestartet\u2026", "zh": "\u6b63\u5728\u542f\u52a8\u540e\u7aef\u2026", "fr": "D\u00e9marrage du backend\u2026"},
    "check_ol": {"en": "Checking Ollama\u2026", "es": "Comprobando Ollama\u2026",
                 "de": "Ollama wird gepr\u00fcft\u2026", "zh": "\u6b63\u5728\u68c0\u67e5 Ollama\u2026", "fr": "V\u00e9rification d'Ollama\u2026"},
    "ol_ok":    {"en": "Ollama connected \u00b7 loading interface\u2026", "es": "Ollama conectado \u00b7 cargando interfaz\u2026",
                 "de": "Ollama verbunden \u00b7 Oberfl\u00e4che l\u00e4dt\u2026", "zh": "Ollama \u5df2\u8fde\u63a5 \u00b7 \u52a0\u8f7d\u754c\u9762\u2026", "fr": "Ollama connect\u00e9 \u00b7 chargement\u2026"},
    "ol_no":    {"en": "Ollama not detected \u00b7 loading interface\u2026", "es": "Ollama no detectado \u00b7 cargando interfaz\u2026",
                 "de": "Ollama nicht erkannt \u00b7 Oberfl\u00e4che l\u00e4dt\u2026", "zh": "\u672a\u68c0\u6d4b\u5230 Ollama \u00b7 \u52a0\u8f7d\u754c\u9762\u2026", "fr": "Ollama non d\u00e9tect\u00e9 \u00b7 chargement\u2026"},
    "ready":    {"en": "Ready", "es": "Listo", "de": "Bereit", "zh": "\u5c31\u7eea", "fr": "Pr\u00eat"},
}
_LANG = _detect_lang()


def _tr(key: str) -> str:
    return _SPLASH_I18N.get(key, {}).get(_LANG) or _SPLASH_I18N.get(key, {}).get("en", key)
# En Lite la cuenta es OPCIONAL y la app es 100% local: NO se exige login.
# (En Pro multiusuario esto se activaría, pero Lite nunca debe bloquear la API.)
os.environ.setdefault("ANDROMEDA_AUTH_REQUIRED", "0")   # Lite: sin gate de login
os.environ.setdefault("ANDROMEDA_TELEMETRY_DB_PATH", str(DATA_DIR / "telemetry.db"))
os.environ.setdefault("ANDROMEDA_MLOPS_DB_PATH", str(DATA_DIR / "mlops_runs.db"))
os.environ.setdefault("ANDROMEDA_MEMORY_DB_PATH", str(DATA_DIR / "memory.db"))
os.environ.setdefault("ANDROMEDA_SPECIALISTS_WRITABLE_PATH", str(DATA_DIR / "specialists.yaml"))
os.environ.setdefault("ANDROMEDA_SPECIALISTS_CONFIG_PATH", str(ROOT / "config" / "specialists.yaml"))
os.environ.setdefault("ANDROMEDA_HARDWARE_POLICIES_PATH", str(ROOT / "config" / "hardware_policies.yaml"))
os.environ.setdefault("ANDROMEDA_MCP_SERVERS_PATH", str(ROOT / "config" / "mcp_servers.yaml"))
# En desktop, Ollama vive en localhost (no en la red Docker "ollama")
os.environ.setdefault("ANDROMEDA_OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def wake_ollama():
    """Intenta DESPERTAR Ollama si no está respondiendo.

    Al abrir Andromeda no debemos obligar al usuario a abrir Ollama a mano: si el
    servicio no responde en localhost:11434, lanzamos `ollama serve` en segundo
    plano (o el binario en sus rutas típicas de instalación). Es best-effort: si
    Ollama no está instalado, no pasa nada y el onboarding lo guiará.
    """
    import urllib.request
    import subprocess
    import shutil

    def _reachable() -> bool:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:11434/api/tags", timeout=2):
                return True
        except Exception:
            return False

    if _reachable():
        print("Ollama ya está corriendo.")
        return

    # Buscar el ejecutable: PATH primero, luego rutas típicas por SO.
    candidates = []
    on_path = shutil.which("ollama")
    if on_path:
        candidates.append(on_path)
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [
            os.path.join(local, "Programs", "Ollama", "ollama.exe"),
            os.path.join(local, "Programs", "Ollama", "ollama app.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
        ]
    elif sys.platform == "darwin":
        candidates += ["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama",
                       "/Applications/Ollama.app/Contents/Resources/ollama"]
    else:
        candidates += ["/usr/local/bin/ollama", "/usr/bin/ollama"]

    exe = next((c for c in candidates if c and os.path.exists(c)), None)
    if not exe:
        print("Ollama no encontrado en el sistema — el onboarding guiará la instalación.")
        return

    try:
        flags = 0
        kwargs = {}
        if sys.platform.startswith("win"):
            # CREATE_NO_WINDOW + STARTUPINFO oculto: el método más fiable para que
            # 'ollama serve' (y sus subprocesos) no parpadeen como ventanas cmd.
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["creationflags"] = flags
            kwargs["startupinfo"] = si
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([exe, "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        print(f"Ollama lanzado desde: {exe}")
        # Esperar a que levante (hasta ~12s).
        for _ in range(12):
            time.sleep(1)
            if _reachable():
                print("Ollama respondió tras el arranque.")
                return
        print("Ollama lanzado pero aún no responde (puede tardar).")
    except Exception as e:
        print(f"No se pudo lanzar Ollama automáticamente: {e}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def stable_port() -> int:
    """Puerto ESTABLE entre arranques.

    Crítico: el navegador asocia localStorage (tema, idioma, conversaciones,
    sesión) al ORIGEN, que incluye el puerto. Si el puerto cambia en cada
    arranque, el webview no encuentra los datos guardados y parece que "se
    borra todo".

    Probamos SIEMPRE la misma lista de puertos en el mismo orden. Solo si
    todos están ocupados (rarísimo) caemos a uno aleatorio — pero entonces
    avisamos en el log de que la persistencia puede verse afectada.
    """
    for candidate in (8771, 8772, 8773, 8774, 8775):
        if _port_is_free(candidate):
            return candidate
    p = free_port()
    print(f"[WARN] Todos los puertos fijos ocupados; usando {p}. "
          f"La persistencia (tema/chats) podría no mantenerse entre arranques.")
    return p


PORT = stable_port()
_backend_error: list[str] = []   # si el backend crashea, el traceback acaba aquí


def run_backend():
    try:
        import uvicorn
        from app import create_app
        # log_config=None: evita que uvicorn reconfigure logging hacia streams
        # de consola que no existen en modo ventana
        uvicorn.run(create_app(), host="127.0.0.1", port=PORT,
                    log_level="warning", log_config=None)
    except Exception:
        tb = traceback.format_exc()
        _backend_error.append(tb)
        print("BACKEND CRASH:\n" + tb)


def wait_for_backend(timeout: float = 40.0) -> bool:
    import urllib.error
    import urllib.request
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{PORT}/api/health/hardware"
    while time.time() < deadline:
        if _backend_error:
            return False                      # crasheó: no esperar más
        try:
            with urllib.request.urlopen(url, timeout=5):
                return True
        except urllib.error.HTTPError:
            return True                       # respuesta HTTP = backend vivo
        except Exception:
            time.sleep(0.3)
    return False


def error_html() -> str:
    detail = (_backend_error[0] if _backend_error else "Timeout esperando al backend.")
    detail = detail.replace("<", "&lt;").replace(">", "&gt;")[-3000:]
    return f"""
    <body style="font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0f;color:#eee;padding:28px">
      <h2 style="color:#f87171">Andromeda no pudo arrancar</h2>
      <p>Copia este log y mándalo para diagnóstico. También está guardado en:</p>
      <code style="color:#fbbf24">{LOG_PATH}</code>
      <pre style="background:#16161d;padding:14px;border-radius:10px;font-size:11px;
                  white-space:pre-wrap;margin-top:14px;color:#fca5a5">{detail}</pre>
    </body>"""


SPLASH_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background:#0a0a0f; color:#f0f0f4; height:100vh; overflow:hidden;
    font-family:-apple-system,'Segoe UI',sans-serif;
    display:flex; align-items:center; justify-content:center;
  }
  .orb { position:fixed; border-radius:50%; filter:blur(90px); opacity:0.45; }
  .o1 { width:420px; height:420px; background:#ff7a6b; top:-12%; left:-8%;
        animation:drift 13s ease-in-out infinite alternate; }
  .o2 { width:380px; height:380px; background:#7b5bd6; bottom:-15%; right:-6%;
        animation:drift 17s ease-in-out infinite alternate-reverse; }
  .o3 { width:300px; height:300px; background:#4a7dd6; top:35%; right:20%;
        animation:drift 21s ease-in-out infinite alternate; }
  @keyframes drift { from { transform:translate(0,0) scale(1); }
                     to   { transform:translate(40px,-30px) scale(1.12); } }
  .box { text-align:center; z-index:2; width:min(440px,86vw); }
  h1 {
    font-family:Georgia,'Times New Roman',serif; font-weight:600;
    font-size:46px; letter-spacing:0.04em; margin-bottom:6px;
    background:linear-gradient(100deg,#ff7a6b 0%,#b06bd6 48%,#4a7dd6 100%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
    animation:fadeUp 0.9s cubic-bezier(0.22,1,0.36,1) backwards;
  }
  .sub { font-size:12px; color:#8a8a96; letter-spacing:0.3em;
         text-transform:uppercase; margin-bottom:46px;
         animation:fadeUp 0.9s 0.15s cubic-bezier(0.22,1,0.36,1) backwards; }
  .track { height:5px; border-radius:999px; background:rgba(255,255,255,0.07);
           overflow:hidden; border:1px solid rgba(255,255,255,0.08);
           animation:fadeUp 0.9s 0.3s cubic-bezier(0.22,1,0.36,1) backwards; }
  .fill { height:100%; width:4%; border-radius:999px;
          background:linear-gradient(90deg,#ff7a6b,#b06bd6,#4a7dd6);
          transition:width 0.7s cubic-bezier(0.22,1,0.36,1);
          position:relative; overflow:hidden; }
  .fill::after { content:''; position:absolute; inset:0;
    background:linear-gradient(105deg,transparent 30%,rgba(255,255,255,0.4) 50%,transparent 70%);
    animation:shim 1.5s ease-in-out infinite; }
  @keyframes shim { from { transform:translateX(-100%);} to { transform:translateX(100%);} }
  .status { margin-top:16px; font-size:12.5px; color:#a8a8b2; min-height:18px;
            animation:fadeUp 0.9s 0.4s cubic-bezier(0.22,1,0.36,1) backwards; }
  @keyframes fadeUp { from { opacity:0; transform:translateY(14px);} to { opacity:1; transform:none;} }
</style></head><body>
  <div class="pywebview-drag-region" style="position:fixed;top:0;left:0;right:48px;height:40px;z-index:9"></div>
  <div onclick="window.pywebview && window.pywebview.api.close()"
       style="position:fixed;top:8px;right:10px;width:30px;height:30px;z-index:10;display:flex;align-items:center;justify-content:center;color:#8a8a96;cursor:pointer;font-size:15px;border-radius:8px"
       onmouseover="this.style.background='rgba(255,255,255,0.08)'" onmouseout="this.style.background='none'">&#10005;</div>
  <div class="orb o1"></div><div class="orb o2"></div><div class="orb o3"></div>
  <div class="box">
    <h1>Andromeda</h1>
    <div class="sub">__SPLASH_SUB__</div>
    <div class="track"><div class="fill" id="bar"></div></div>
    <div class="status" id="st">__SPLASH_INIT__</div>
  </div>
  <script>
    function setStage(pct, txt) {
      document.getElementById('bar').style.width = pct + '%';
      document.getElementById('st').textContent = txt;
    }
  </script>
</body></html>"""



class WindowApi:
    """API expuesta al frontend (window.pywebview.api) para la barra de título.

    El estado de maximización se rastrea explícitamente. En pywebview, maximize()
    y restore() existen en todas las plataformas modernas, pero el usuario puede
    desincronizar el estado con gestos nativos; por eso guardamos geometría previa
    y la restauramos a mano si la API nativa no responde."""
    def __init__(self):
        self._win = None
        self._maximized = False
        self._prev_geom = None     # (x, y, w, h) antes de maximizar

    def minimize(self):
        try:
            if self._win:
                self._win.minimize()
        except Exception:
            pass

    def _nswindow(self):
        """Devuelve el NSWindow real de Cocoa por debajo de pywebview, o None.
        Lo usamos para maximizar contra el MONITOR donde está la ventana ahora
        mismo (pywebview cachea la pantalla inicial y deja huecos al mover la
        ventana a otro monitor de distinta resolución)."""
        try:
            from webview.platforms.cocoa import BrowserView
            inst = BrowserView.instances.get(self._win.uid)
            return inst.window if inst else None
        except Exception:
            return None

    def _enable_native_fullscreen(self):
        """Permite que una ventana frameless entre en fullscreen real de macOS
        (espacio propio). Sin esto, una ventana sin marco no responde a
        toggleFullScreen_ ni al botón verde."""
        nswin = self._nswindow()
        if nswin is None:
            return False
        try:
            import AppKit
            from PyObjCTools import AppHelper
            def _setup():
                # Comportamiento: participa en fullscreen primario + permite el botón verde
                behavior = (AppKit.NSWindowCollectionBehaviorFullScreenPrimary
                            | AppKit.NSWindowCollectionBehaviorManaged)
                nswin.setCollectionBehavior_(behavior)
                # La ventana debe poder redimensionarse para entrar en fullscreen
                style = nswin.styleMask() | AppKit.NSWindowStyleMaskResizable
                nswin.setStyleMask_(style)
            AppHelper.callAfter(_setup)
            return True
        except Exception:
            return False

    def _do_maximize(self):
        # Guarda geometría actual para poder restaurar con precisión
        try:
            self._prev_geom = (self._win.x, self._win.y, self._win.width, self._win.height)
        except Exception:
            self._prev_geom = None

        # ── macOS: FULLSCREEN REAL (espacio propio, como el botón verde). ──
        nswin = self._nswindow()
        if nswin is not None:
            try:
                import AppKit
                from PyObjCTools import AppHelper
                def _fs():
                    # Asegura el collectionBehavior antes de alternar
                    behavior = (AppKit.NSWindowCollectionBehaviorFullScreenPrimary
                                | AppKit.NSWindowCollectionBehaviorManaged)
                    nswin.setCollectionBehavior_(behavior)
                    style = nswin.styleMask() | AppKit.NSWindowStyleMaskResizable
                    nswin.setStyleMask_(style)
                    # Solo entrar si no estamos ya en fullscreen
                    is_fs = (nswin.styleMask() & AppKit.NSWindowStyleMaskFullScreen) != 0
                    if not is_fs:
                        nswin.toggleFullScreen_(None)
                AppHelper.callAfter(_fs)
                self._maximized = True
                return
            except Exception:
                pass

        # ── Otras plataformas (Windows .exe usa WindowState nativo): API estándar ──
        try:
            self._win.maximize()
            self._maximized = True
        except Exception:
            pass

    def _do_restore(self):
        # ── macOS: salir de fullscreen real ──
        nswin = self._nswindow()
        if nswin is not None:
            try:
                import AppKit
                from PyObjCTools import AppHelper
                def _exit_fs():
                    is_fs = (nswin.styleMask() & AppKit.NSWindowStyleMaskFullScreen) != 0
                    if is_fs:
                        nswin.toggleFullScreen_(None)
                AppHelper.callAfter(_exit_fs)
                self._maximized = False
                return
            except Exception:
                pass

        # Otras plataformas
        try:
            self._win.restore()
        except Exception:
            pass
        if self._prev_geom:
            try:
                x, y, w, h = self._prev_geom
                self._win.resize(w, h)
                self._win.move(x, y)
            except Exception:
                pass
        self._maximized = False

    def toggle_maximize(self):
        if not self._win:
            return
        if self._maximized:
            self._do_restore()
        else:
            self._do_maximize()

    def is_maximized(self):
        return self._maximized

    def close(self):
        # destroy() y, si el loop de Cocoa/Win no muere (pasa en macOS),
        # salida dura garantizada medio segundo después.
        try:
            if self._win:
                self._win.destroy()
        except Exception:
            pass
        threading.Timer(0.5, lambda: os._exit(0)).start()


def main():
    import webview

    t = threading.Thread(target=run_backend, daemon=True)
    t.start()

    # Ventana única: primero splash, luego navega a la app
    api = WindowApi()
    window = webview.create_window(
        "Andromeda",
        html=SPLASH_HTML.replace("__SPLASH_SUB__", _tr("sub")).replace("__SPLASH_INIT__", _tr("init")),
        width=1380, height=860,
        min_size=(980, 640),
        background_color="#0a0a0f",
        frameless=True,
        easy_drag=False,
        js_api=api,
    )
    api._win = window

    def stage(pct, txt):
        try:
            window.evaluate_js(f"setStage({pct}, {txt!r})")
        except Exception:
            pass

    def _safe_eval(win, js):
        try:
            win.evaluate_js(js)
        except Exception:
            pass

    def boot_monitor():
        time.sleep(0.6)                       # dejar que el splash pinte
        stage(18, _tr("backend"))
        ok = wait_for_backend()
        print(f"Backend listo: {ok} (puerto {PORT})")
        if not ok:
            try:
                window.load_html(error_html())
            except Exception:
                pass
            return
        stage(62, _tr("check_ol"))
        # Despertar Ollama si no está corriendo (best-effort, en este mismo hilo
        # del monitor de arranque para que el splash refleje el progreso).
        try:
            wake_ollama()
        except Exception:
            pass
        # Sondeo no bloqueante de Ollama: solo informativo para el splash
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=8):
                stage(82, _tr("ol_ok"))
        except Exception:
            stage(82, _tr("ol_no"))
        time.sleep(0.4)
        stage(100, _tr("ready"))
        time.sleep(0.35)
        window.load_url(f"http://127.0.0.1:{PORT}")
        # Marca para que el frontend sepa que corre dentro del binario de
        # escritorio (pywebview) y use el modo de chat sin streaming, que es
        # el que funciona en WKWebView. Reintentamos por si la página tarda.
        for _delay in (0.8, 1.6, 2.5):
            threading.Timer(_delay, lambda: _safe_eval(window,
                "window.__ANDROMEDA_DESKTOP__ = true")).start()

    threading.Thread(target=boot_monitor, daemon=True).start()

    # En cuanto la ventana se muestra, habilitamos el fullscreen real de macOS
    # (necesario en ventanas frameless; sin esto el botón verde / toggle no entra).
    def _on_shown():
        try:
            api._enable_native_fullscreen()
        except Exception:
            pass
    try:
        window.events.shown += _on_shown
    except Exception:
        pass

    # CRÍTICO: por defecto pywebview arranca en modo privado y BORRA el
    # localStorage/cookies al cerrar — eso hacía que se perdieran la sesión,
    # la configuración de diseño y las conversaciones. Con private_mode=False
    # y un storage_path persistente, el webview guarda todo entre aperturas.
    import os as _os
    _storage = _os.path.join(
        _os.environ.get("ANDROMEDA_DATA_DIR") or _os.path.expanduser("~/.andromeda"),
        "webview",
    )
    try:
        _os.makedirs(_storage, exist_ok=True)
    except Exception:
        _storage = None

    webview.start(private_mode=False, storage_path=_storage)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # obligatorio en .exe de Windows
    try:
        main()
    except Exception:
        print("FATAL:\n" + traceback.format_exc())
        raise
