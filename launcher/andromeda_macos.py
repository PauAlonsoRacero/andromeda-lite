"""
andromeda_macos.py — Launcher de Andromeda para macOS.
Se compila con PyInstaller en un .app standalone.

Flujo idéntico al Windows pero usando rutas y comandos macOS.
"""

import os
import sys
import time
import subprocess
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launcher_core import (
    banner, step, ok, warn, err,
    get_install_dir, is_docker_running, is_backend_ready,
    wait_for_backend, run_docker_compose, open_browser,
    green, yellow, red, cyan, bold,
    FRONTEND_URL, BACKEND_URL,
)

def start_docker_desktop_mac():
    """Arranca Docker Desktop en macOS."""
    # Intentar via 'open'
    result = subprocess.run(
        ["open", "-a", "Docker"],
        capture_output=True
    )
    if result.returncode != 0:
        # Intentar ruta directa
        paths = [
            "/Applications/Docker.app",
            os.path.expanduser("~/Applications/Docker.app"),
        ]
        for path in paths:
            if os.path.exists(path):
                subprocess.Popen(["open", path])
                return True
    return result.returncode == 0

def cleanup_old_containers(install_dir):
    subprocess.run(
        ["docker", "rm", "-f",
         "andromeda-ollama", "andromeda-backend", "andromeda-frontend"],
        capture_output=True, cwd=install_dir
    )

def main():
    os.system("clear")
    banner()

    install_dir = get_install_dir()
    print(f"  Directorio: {install_dir}\n")

    # ── 1. Docker ─────────────────────────────────────────────────────────────
    step("1/4", "Verificando Docker Desktop...")

    if is_docker_running():
        ok("Docker está corriendo")
    else:
        warn("Docker no está corriendo — iniciando...")
        start_docker_desktop_mac()

        print("  Esperando que Docker arranque", end="", flush=True)
        for i in range(40):
            time.sleep(3)
            print(".", end="", flush=True)
            if is_docker_running():
                print()
                ok("Docker listo")
                break
        else:
            print()
            err("Docker tardó demasiado.")
            print()
            print(yellow("  Abre Docker Desktop desde Applications y espera"))
            print(yellow("  a que el icono de la barra superior deje de moverse."))
            print()
            input("  Presiona Enter cuando Docker esté listo...")
            if not is_docker_running():
                err("Docker sigue sin responder.")
                input("\n  Presiona Enter para salir...")
                sys.exit(1)

    # ── 2. Ya está corriendo? ─────────────────────────────────────────────────
    step("2/4", "Verificando estado de Andromeda...")

    if is_backend_ready():
        ok("Andromeda ya está corriendo")
        print()
        _show_ready()
        threading.Thread(target=open_browser, daemon=True).start()
        _menu_loop(install_dir)
        return

    # ── 3. Arrancar contenedores ──────────────────────────────────────────────
    step("3/4", "Arrancando Andromeda...")

    cleanup_old_containers(install_dir)
    success, stdout, stderr = run_docker_compose(install_dir, "up")

    if not success and "already in use" in stderr:
        cleanup_old_containers(install_dir)
        success, stdout, stderr = run_docker_compose(install_dir, "up")

    if not success:
        err(f"Error: {stderr[:200]}")
        print()
        print(yellow("  Intenta manualmente en Terminal:"))
        print(f"  cd \"{install_dir}\"")
        print("  docker-compose up -d")
        input("\n  Presiona Enter para salir...")
        sys.exit(1)

    ok("Contenedores arrancados")

    # ── 4. Esperar backend ────────────────────────────────────────────────────
    step("4/4", "Esperando que el sistema esté listo...")
    print("  (El navegador se abrirá automáticamente)")
    print()

    start = time.time()
    dots = 0
    while True:
        if is_backend_ready():
            break
        elapsed = int(time.time() - start)
        dots = (dots + 1) % 4
        print(f"\r  Iniciando{'.' * dots}{' ' * (3-dots)}  ({elapsed}s)", end="", flush=True)
        time.sleep(2)
        if elapsed > 120:
            print()
            warn("Tardó más de lo esperado. Abriendo navegador de todas formas...")
            break

    print()
    ok(f"Sistema listo en {int(time.time()-start)}s")

    threading.Thread(target=open_browser, daemon=True).start()
    _show_ready()
    _menu_loop(install_dir)


def _show_ready():
    print()
    print(green("  ╔══════════════════════════════════════════════════════╗"))
    print(green("  ║   ✦  Andromeda está listo                           ║"))
    print(green("  ║                                                      ║"))
    print(green(f"  ║   UI:     {FRONTEND_URL:<43}║"))
    print(green(f"  ║   API:    http://localhost:8000/docs{' '*18}║"))
    print(green("  ╚══════════════════════════════════════════════════════╝"))
    print()


def _menu_loop(install_dir):
    print(yellow("  Opciones:"))
    print("    [A] Abrir en el navegador")
    print("    [L] Ver logs del backend")
    print("    [R] Reiniciar Andromeda")
    print("    [S] Parar Andromeda")
    print("    [Q] Salir (Andromeda sigue corriendo)")
    print()

    while True:
        try:
            cmd = input("  > ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd == "A":
            open_browser()
        elif cmd == "L":
            print(cyan("  Logs del backend (Ctrl+C para parar):"))
            try:
                subprocess.run(
                    ["docker-compose", "logs", "-f", "--tail=50", "backend"],
                    cwd=install_dir
                )
            except KeyboardInterrupt:
                print()
        elif cmd == "R":
            print(yellow("  Reiniciando..."))
            subprocess.run(["docker-compose", "restart"], cwd=install_dir, capture_output=True)
            ok("Reiniciado")
        elif cmd == "S":
            print(yellow("  Parando Andromeda..."))
            run_docker_compose(install_dir, "down")
            ok("Andromeda parado")
            input("  Presiona Enter para salir...")
            break
        elif cmd == "Q":
            print(yellow("  Saliendo (Andromeda sigue corriendo en background)"))
            print(f"  Accede en: {FRONTEND_URL}")
            break


if __name__ == "__main__":
    main()
