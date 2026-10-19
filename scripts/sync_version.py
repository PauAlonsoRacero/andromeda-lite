#!/usr/bin/env python3
"""
sync_version.py — Propaga la versión de VERSION a frontend y backend.

Fuente única de verdad: el archivo VERSION en la raíz. Ejecuta esto tras
cambiar la versión (o en CI al crear un tag) para que frontend/version.js y
backend/app/config.py queden coherentes.

Uso:  python scripts/sync_version.py [nueva_version]
      (sin argumento usa el contenido actual de VERSION)
"""
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"


def main():
    if len(sys.argv) > 1:
        version = sys.argv[1].lstrip("v").strip()
        VERSION_FILE.write_text(version + "\n")
    else:
        version = VERSION_FILE.read_text().strip()

    build = datetime.now().strftime("%Y%m%d")

    # frontend/src/version.js
    vjs = ROOT / "frontend" / "src" / "version.js"
    if vjs.exists():
        s = vjs.read_text()
        s = re.sub(r"APP_VERSION = '[^']*'", f"APP_VERSION = '{version}'", s)
        s = re.sub(r"APP_BUILD = '[^']*'", f"APP_BUILD = '{build}'", s)
        vjs.write_text(s)
        print(f"✓ frontend/src/version.js → {version} (build {build})")

    # backend/app/config.py
    cfg = ROOT / "backend" / "app" / "config.py"
    if cfg.exists():
        s = cfg.read_text()
        s = re.sub(r'app_version: str = Field\(default="[^"]*"',
                   f'app_version: str = Field(default="{version}"', s)
        cfg.write_text(s)
        print(f"✓ backend/app/config.py → {version}")

    # frontend/package.json — se quedaba fuera de la sincronización, así que
    # divergía en silencio (llegó a estar en 2.2.0 con el resto en 1.0.0).
    pkg = ROOT / "frontend" / "package.json"
    if pkg.exists():
        s = pkg.read_text()
        s = re.sub(r'"version":\s*"[^"]*"', f'"version": "{version}"', s, count=1)
        pkg.write_text(s)
        print(f"✓ frontend/package.json → {version}")

    print(f"\nVersión sincronizada: {version}")


if __name__ == "__main__":
    main()
