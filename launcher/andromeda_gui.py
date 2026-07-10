"""
andromeda_gui.py — Launcher GUI de Andromeda.

Ventana nativa (tkinter) que:
  1. Verifica Docker (lo arranca si hace falta)
  2. Levanta los contenedores
  3. Descarga los modelos iniciales si no están
  4. Abre el navegador automáticamente
  5. Muestra el estado en tiempo real

Se compila a .exe con PyInstaller. Doble clic y todo arranca solo.
"""
import os
import sys
import time
import threading
import queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launcher_core import (
    ANDROMEDA_VERSION, FRONTEND_URL,
    get_install_dir, is_docker_installed, is_docker_running,
    start_docker_desktop, wait_for_docker,
    is_backend_ready, wait_for_backend, get_backend_status,
    run_docker_compose, get_running_containers,
    get_installed_models, pull_model, missing_starter_models,
    open_browser, STARTER_MODELS,
)

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    HAS_TK = True
except ImportError:
    HAS_TK = False


# Paleta visual (deep space, igual que la app)
BG       = "#060810"
SURFACE  = "#12151f"
BORDER   = "#252a38"
TEXT     = "#e8eaf0"
TEXT_DIM = "#8b92a8"
BLUE     = "#5b9cf6"
PURPLE   = "#a78bfa"
TEAL     = "#00d4aa"
GREEN    = "#34d399"
AMBER    = "#fbbf24"
RED      = "#f87171"


class AndromedaLauncher:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.install_dir = get_install_dir()
        self.running = False
        self._setup_ui()
        self.root.after(100, self._process_queue)

    def _setup_ui(self):
        self.root.title("Andromeda Launcher")
        self.root.configure(bg=BG)
        self.root.geometry("620x540")
        self.root.resizable(False, False)

        # Header
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=30, pady=(26, 12))

        tk.Label(header, text="✦ ANDROMEDA", font=("Segoe UI", 22, "bold"),
                 fg=BLUE, bg=BG).pack(anchor="w")
        tk.Label(header, text=f"AI Orchestration Platform · v{ANDROMEDA_VERSION}",
                 font=("Segoe UI", 10), fg=TEXT_DIM, bg=BG).pack(anchor="w")

        # Status indicator
        self.status_frame = tk.Frame(self.root, bg=SURFACE, highlightbackground=BORDER,
                                      highlightthickness=1)
        self.status_frame.pack(fill="x", padx=30, pady=8)

        self.status_dot = tk.Label(self.status_frame, text="●", font=("Segoe UI", 14),
                                   fg=TEXT_DIM, bg=SURFACE)
        self.status_dot.pack(side="left", padx=(14, 8), pady=12)

        self.status_label = tk.Label(self.status_frame, text="Listo para iniciar",
                                     font=("Segoe UI", 11), fg=TEXT, bg=SURFACE)
        self.status_label.pack(side="left", pady=12)

        # Progress bar
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Andromeda.Horizontal.TProgressbar",
                       troughcolor=SURFACE, background=BLUE, borderwidth=0,
                       lightcolor=BLUE, darkcolor=BLUE)
        self.progress = ttk.Progressbar(self.root, mode="determinate",
                                       style="Andromeda.Horizontal.TProgressbar",
                                       maximum=100)
        self.progress.pack(fill="x", padx=30, pady=4)

        # Log console
        self.log = scrolledtext.ScrolledText(
            self.root, height=14, font=("Consolas", 9),
            bg="#0a0d16", fg=TEXT_DIM, insertbackground=TEXT,
            relief="flat", borderwidth=0, padx=12, pady=10,
        )
        self.log.pack(fill="both", expand=True, padx=30, pady=10)
        self.log.tag_config("ok",    foreground=GREEN)
        self.log.tag_config("warn",  foreground=AMBER)
        self.log.tag_config("err",   foreground=RED)
        self.log.tag_config("info",  foreground=BLUE)
        self.log.tag_config("dim",   foreground=TEXT_DIM)

        # Buttons
        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=30, pady=(0, 20))

        self.start_btn = tk.Button(
            btns, text="▶  Iniciar Andromeda", font=("Segoe UI", 11, "bold"),
            bg=BLUE, fg="white", relief="flat", cursor="hand2",
            activebackground=PURPLE, activeforeground="white",
            padx=20, pady=10, command=self.on_start,
        )
        self.start_btn.pack(side="left")

        self.open_btn = tk.Button(
            btns, text="🌐  Abrir navegador", font=("Segoe UI", 10),
            bg=SURFACE, fg=TEXT, relief="flat", cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            padx=16, pady=10, command=lambda: open_browser(), state="disabled",
        )
        self.open_btn.pack(side="left", padx=8)

        self.stop_btn = tk.Button(
            btns, text="■  Parar", font=("Segoe UI", 10),
            bg=SURFACE, fg=TEXT_DIM, relief="flat", cursor="hand2",
            activebackground=BORDER, padx=16, pady=10,
            command=self.on_stop, state="disabled",
        )
        self.stop_btn.pack(side="right")

        self._log("Bienvenido a Andromeda. Pulsa 'Iniciar' para arrancar todo.", "dim")

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg, tag="dim"):
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")

    def _set_status(self, text, color=TEXT_DIM):
        self.status_label.config(text=text)
        self.status_dot.config(fg=color)

    def _set_progress(self, value):
        self.progress["value"] = value

    # ── Queue para thread-safe UI updates ───────────────────────────────────────

    def _emit(self, kind, *args):
        self.q.put((kind, args))

    def _process_queue(self):
        try:
            while True:
                kind, args = self.q.get_nowait()
                if kind == "log":     self._log(*args)
                elif kind == "status": self._set_status(*args)
                elif kind == "progress": self._set_progress(*args)
                elif kind == "done":   self._on_done(*args)
                elif kind == "enable_open": self.open_btn.config(state="normal")
                elif kind == "enable_stop": self.stop_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    # ── Acciones ────────────────────────────────────────────────────────────────

    def on_start(self):
        self.start_btn.config(state="disabled")
        self.running = True
        threading.Thread(target=self._startup_sequence, daemon=True).start()

    def on_stop(self):
        self._emit("log", "Parando contenedores...", "warn")
        threading.Thread(target=self._stop_sequence, daemon=True).start()

    def _stop_sequence(self):
        run_docker_compose(self.install_dir, action="down")
        self._emit("log", "Andromeda detenido.", "dim")
        self._emit("status", "Detenido", TEXT_DIM)
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.open_btn.config(state="disabled"))

    def _startup_sequence(self):
        """Secuencia completa de arranque, en un thread."""

        # ── 1. Docker instalado ────────────────────────────────────────────────
        self._emit("status", "Verificando Docker...", AMBER)
        self._emit("progress", 5)
        if not is_docker_installed():
            self._emit("log", "Docker no está instalado.", "err")
            self._emit("log", "Descárgalo de: https://docker.com/products/docker-desktop", "info")
            self._emit("status", "Docker no instalado", RED)
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return
        self._emit("log", "Docker instalado.", "ok")

        # ── 2. Docker corriendo ─────────────────────────────────────────────────
        self._emit("progress", 12)
        if not is_docker_running():
            self._emit("log", "Docker Desktop no está corriendo. Arrancándolo...", "warn")
            self._emit("status", "Arrancando Docker Desktop...", AMBER)
            if start_docker_desktop():
                self._emit("log", "Esperando a que Docker arranque (puede tardar 1 min)...", "dim")
                if not wait_for_docker(120):
                    self._emit("log", "Docker tardó demasiado en arrancar.", "err")
                    self._emit("status", "Error con Docker", RED)
                    self.root.after(0, lambda: self.start_btn.config(state="normal"))
                    return
            else:
                self._emit("log", "No se pudo arrancar Docker Desktop automáticamente.", "err")
                self._emit("log", "Ábrelo manualmente y vuelve a intentarlo.", "info")
                self._emit("status", "Abre Docker manualmente", RED)
                self.root.after(0, lambda: self.start_btn.config(state="normal"))
                return
        self._emit("log", "Docker está corriendo.", "ok")

        # ── 3. Levantar contenedores ────────────────────────────────────────────
        self._emit("progress", 25)
        self._emit("status", "Levantando contenedores...", AMBER)
        self._emit("log", "Iniciando Ollama, backend y frontend...", "dim")

        # Detectar si las imágenes existen; si no, build
        containers = get_running_containers()
        need_build = len(containers) == 0
        success, stdout, stderr = run_docker_compose(
            self.install_dir, action="up", build=need_build
        )
        if not success:
            self._emit("log", "Error al levantar contenedores:", "err")
            self._emit("log", (stderr or stdout)[:400], "dim")
            self._emit("status", "Error en docker-compose", RED)
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return
        self._emit("log", "Contenedores levantados.", "ok")
        self._emit("enable_stop")

        # ── 4. Esperar al backend ───────────────────────────────────────────────
        self._emit("progress", 45)
        self._emit("status", "Esperando al backend...", AMBER)
        self._emit("log", "Esperando a que el backend responda...", "dim")
        if not wait_for_backend(180):
            self._emit("log", "El backend no respondió a tiempo.", "err")
            self._emit("log", "Revisa los logs con: docker logs andromeda-backend", "info")
            self._emit("status", "Backend no responde", RED)
            return
        self._emit("log", "Backend listo.", "ok")

        # ── 5. Modelos iniciales ────────────────────────────────────────────────
        self._emit("progress", 60)
        self._emit("status", "Comprobando modelos de IA...", AMBER)
        missing = missing_starter_models()

        if missing:
            self._emit("log", f"Faltan {len(missing)} modelos iniciales. Descargando...", "warn")
            self._emit("log", "(Solo la primera vez — pueden ser varios GB)", "dim")
            total = len(missing)
            for i, (model, role) in enumerate(missing):
                self._emit("status", f"Descargando {model}...", AMBER)
                self._emit("log", f"  Descargando {model} ({role})...", "info")

                def progress_cb(line):
                    if "pulling" in line.lower() or "%" in line:
                        self._emit("status", f"{model}: {line[:40]}", AMBER)

                pull_model(model, on_progress=progress_cb)
                self._emit("log", f"  {model} listo.", "ok")
                self._emit("progress", 60 + int((i+1)/total * 30))
        else:
            self._emit("log", "Todos los modelos iniciales ya están descargados.", "ok")

        # ── 6. Abrir navegador ──────────────────────────────────────────────────
        self._emit("progress", 95)
        self._emit("status", "Abriendo navegador...", TEAL)
        self._emit("log", "Abriendo Andromeda en el navegador...", "info")
        open_browser()

        self._emit("progress", 100)
        self._emit("done")

    def _on_done(self):
        self._set_status("Andromeda funcionando", GREEN)
        self._log("", "dim")
        self._log("✦ Andromeda está listo. Disfruta.", "ok")
        self._log(f"  Abierto en {FRONTEND_URL}", "dim")
        self.open_btn.config(state="normal")


def run_console_fallback():
    """Si tkinter no está disponible, usar modo consola."""
    from launcher_core import banner, step, ok, warn, err
    banner()
    install_dir = get_install_dir()

    step(1, "Verificando Docker")
    if not is_docker_running():
        warn("Docker no corre. Arrancándolo...")
        start_docker_desktop()
        if not wait_for_docker(120):
            err("Docker no arrancó. Ábrelo manualmente.")
            input("Enter para salir...")
            return
    ok("Docker corriendo")

    step(2, "Levantando contenedores")
    success, out, errout = run_docker_compose(install_dir, action="up",
                                              build=len(get_running_containers())==0)
    if not success:
        err(errout[:300]); input("Enter..."); return
    ok("Contenedores levantados")

    step(3, "Esperando backend")
    if not wait_for_backend(180):
        err("Backend no responde"); input("Enter..."); return
    ok("Backend listo")

    step(4, "Modelos iniciales")
    missing = missing_starter_models()
    if missing:
        for model, role in missing:
            print(f"  Descargando {model} ({role})...")
            pull_model(model)
            ok(f"{model} listo")
    else:
        ok("Modelos ya descargados")

    step(5, "Abriendo navegador")
    open_browser()
    ok("Andromeda funcionando")
    print("\n  Pulsa Enter para salir (Andromeda sigue corriendo)...")
    input()


def main():
    if HAS_TK:
        root = tk.Tk()
        AndromedaLauncher(root)
        root.mainloop()
    else:
        run_console_fallback()


if __name__ == "__main__":
    main()
