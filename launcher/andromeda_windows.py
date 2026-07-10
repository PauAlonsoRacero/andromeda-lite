"""
andromeda_windows.py — Launcher de Andromeda para Windows.
Se compila con PyInstaller en un .exe standalone.

Flujo:
  1. Muestra banner
  2. Verifica que Docker Desktop está corriendo
     → Si no está: abre Docker Desktop y espera
  3. Arranca los contenedores con docker-compose
  4. Espera activamente a que el backend responda
  5. Abre el navegador en http://localhost
  6. Queda en un loop de monitorización con menú
"""

import os
import sys
import time
import subprocess
import threading

# Añadir el directorio del launcher al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launcher_core import (
    banner, step, ok, warn, err,
    get_install_dir, is_docker_running, is_backend_ready,
    wait_for_backend, run_docker_compose, open_browser,
    green, yellow, red, cyan, bold,
    FRONTEND_URL, BACKEND_URL,
)

def start_docker_desktop():
    """Intenta arrancar Docker Desktop en Windows."""
    docker_paths = [
        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe"),
    ]
    for path in docker_paths:
        if os.path.exists(path):
            subprocess.Popen([path], shell=False)
            return True
    # Intentar via start
    subprocess.Popen("start Docker Desktop", shell=True)
    return True

def cleanup_old_containers(install_dir):
    """Elimina contenedores huérfanos de sesiones anteriores."""
    subprocess.run(
        ["docker", "rm", "-f",
         "andromeda-ollama", "andromeda-backend", "andromeda-frontend"],
        capture_output=True, cwd=install_dir
    )

def main():
    os.system("cls")  # Limpiar pantalla Windows
    banner()

    install_dir = get_install_dir()
    print(f"  Directorio: {install_dir}\n")

    # ── 1. Docker ─────────────────────────────────────────────────────────────
    step("1/4", "Verificando Docker Desktop...")

    if is_docker_running():
        ok("Docker está corriendo")
    else:
        warn("Docker no está corriendo — iniciando...")
        start_docker_desktop()

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
            err("Docker tardó demasiado en arrancar.")
            print()
            print(yellow("  Solución: Abre Docker Desktop manualmente"))
            print(yellow("  y espera a que aparezca el icono en la barra de tareas."))
            print()
            input("  Presiona Enter cuando Docker esté listo...")
            if not is_docker_running():
                err("Docker sigue sin responder. Cierra este programa, abre Docker Desktop y vuelve a intentarlo.")
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

    # Limpiar posibles contenedores huérfanos
    cleanup_old_containers(install_dir)

    success, stdout, stderr = run_docker_compose(install_dir, "up")

    if not success and "already in use" in stderr:
        warn("Hay contenedores del tipo anterior. Limpiando...")
        cleanup_old_containers(install_dir)
        success, stdout, stderr = run_docker_compose(install_dir, "up")

    if not success:
        err(f"Error arrancando Andromeda: {stderr[:200]}")
        print()
        print(yellow("  Intenta ejecutar manualmente:"))
        print(f"  cd \"{install_dir}\"")
        print("  docker-compose up -d")
        input("\n  Presiona Enter para salir...")
        sys.exit(1)

    ok("Contenedores arrancados")

    # ── 4. Esperar que el backend responda ────────────────────────────────────
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
            warn("El sistema tardó más de lo esperado. Abriendo el navegador de todas formas...")
            break

    print()
    ok(f"Sistema listo en {int(time.time()-start)}s")

    # ── Abrir navegador ───────────────────────────────────────────────────────
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
        else:
            print(f"  Opción desconocida: {cmd}")


if __name__ == "__main__":
    main()
