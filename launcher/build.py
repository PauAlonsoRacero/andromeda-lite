"""
build.py — Script de compilación de los ejecutables de Andromeda.

Genera:
  dist/windows/Andromeda.exe     — Windows 11 64-bit
  dist/macos/Andromeda           — macOS (binary, se convierte a .app manualmente)

Uso:
  python build.py windows   → construye solo para Windows
  python build.py macos     → construye solo para macOS
  python build.py all       → construye ambos (solo en el OS correspondiente)
"""

import sys
import os
import subprocess
import platform
import shutil

OS = platform.system()
BUILD_DIR = os.path.dirname(os.path.abspath(__file__))

def build_windows():
    print("\n[BUILD] Compilando Andromeda.exe para Windows...")
    result = subprocess.run([
        "pyinstaller",
        "--onefile",                          # Todo en un solo .exe
        "--console",                          # Ventana de terminal visible (necesaria para el menú)
        "--name", "Andromeda",
        "--distpath", os.path.join(BUILD_DIR, "dist", "windows"),
        "--workpath", os.path.join(BUILD_DIR, "build_tmp"),
        "--specpath", os.path.join(BUILD_DIR, "build_tmp"),
        "--add-data", f"{os.path.join(BUILD_DIR, 'launcher_core.py')}:.",
        "--hidden-import", "urllib.request",
        "--hidden-import", "webbrowser",
        "--hidden-import", "threading",
        "--hidden-import", "subprocess",
        os.path.join(BUILD_DIR, "andromeda_windows.py"),
    ], cwd=BUILD_DIR)

    if result.returncode == 0:
        exe_path = os.path.join(BUILD_DIR, "dist", "windows", "Andromeda.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"[OK] Andromeda.exe generado ({size_mb:.1f} MB)")
            print(f"     Ruta: {exe_path}")
        return True
    else:
        print("[ERROR] Falló la compilación para Windows")
        return False

def build_macos():
    print("\n[BUILD] Compilando Andromeda para macOS...")
    result = subprocess.run([
        "pyinstaller",
        "--onefile",
        "--console",
        "--name", "Andromeda",
        "--distpath", os.path.join(BUILD_DIR, "dist", "macos"),
        "--workpath", os.path.join(BUILD_DIR, "build_tmp"),
        "--specpath", os.path.join(BUILD_DIR, "build_tmp"),
        "--add-data", f"{os.path.join(BUILD_DIR, 'launcher_core.py')}:.",
        "--hidden-import", "urllib.request",
        "--hidden-import", "webbrowser",
        "--hidden-import", "threading",
        "--hidden-import", "subprocess",
        os.path.join(BUILD_DIR, "andromeda_macos.py"),
    ], cwd=BUILD_DIR)

    if result.returncode == 0:
        bin_path = os.path.join(BUILD_DIR, "dist", "macos", "Andromeda")
        if os.path.exists(bin_path):
            size_mb = os.path.getsize(bin_path) / 1024 / 1024
            print(f"[OK] Andromeda (macOS binary) generado ({size_mb:.1f} MB)")
            print(f"     Ruta: {bin_path}")
            # Hacer ejecutable
            os.chmod(bin_path, 0o755)
        return True
    else:
        print("[ERROR] Falló la compilación para macOS")
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else OS.lower()

    os.makedirs(os.path.join(BUILD_DIR, "dist", "windows"), exist_ok=True)
    os.makedirs(os.path.join(BUILD_DIR, "dist", "macos"),   exist_ok=True)

    if target in ("windows", "all") and OS == "Windows":
        build_windows()
    elif target in ("macos", "darwin", "all") and OS == "Darwin":
        build_macos()
    elif target == "windows" and OS != "Windows":
        print("Cross-compilation Windows → no disponible en este OS.")
        print("Ejecuta build.py en una máquina Windows.")
    elif target in ("macos", "darwin") and OS != "Darwin":
        print("Cross-compilation macOS → no disponible en este OS.")
        print("Ejecuta build.py en una máquina macOS.")
    else:
        print(f"OS detectado: {OS}. Usa: python build.py [windows|macos|all]")
