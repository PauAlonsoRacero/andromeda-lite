#!/usr/bin/env bash
# build_linux.sh — Construye Andromeda.AppImage para Linux.
# Requisitos: Python 3.11+, Node 18+, y dependencias de WebKitGTK para pywebview:
#   Debian/Ubuntu: sudo apt install python3-gi gir1.2-webkit2-4.1 libgirepository1.0-dev
set -e
cd "$(dirname "$0")/.."

echo "▸ 1/4  Frontend"
cd frontend && npm install && npm run build && cd ..

echo "▸ 2/4  Dependencias backend + PyInstaller"
python3 -m pip install -r backend/requirements.txt pyinstaller pywebview[qt] --break-system-packages 2>/dev/null \
  || python3 -m pip install -r backend/requirements.txt pyinstaller "pywebview[qt]"

echo "▸ 3/4  Empaquetado"
pyinstaller build_desktop.spec --noconfirm

echo "▸ 4/4  AppImage (opcional)"
echo "   dist/Andromeda contiene el binario. Para crear un AppImage portable,"
echo "   usa appimagetool sobre dist/Andromeda. Ver packaging/README.md."
