#!/usr/bin/env bash
# build_macos.sh — Construye Andromeda.app para macOS.
# Requisitos: Python 3.11+, Node 18+, y ejecutarlo EN un Mac.
set -e
cd "$(dirname "$0")/.."

echo "▸ 1/4  Frontend"
cd frontend && npm install && npm run build && cd ..

echo "▸ 2/4  Dependencias backend + PyInstaller"
python3 -m pip install -r backend/requirements.txt pyinstaller pywebview pyobjc --break-system-packages 2>/dev/null \
  || python3 -m pip install -r backend/requirements.txt pyinstaller pywebview pyobjc

echo "▸ 3/4  Empaquetado (.app)"
pyinstaller build_desktop.spec --noconfirm

echo "▸ 4/4  Listo"
echo "   → dist/Andromeda.app"
echo "   Para distribuir fuera de tu Mac, fírmala y notarízala con tu Apple Developer ID:"
echo "     codesign --deep --force --options runtime --sign \"Developer ID Application: TU NOMBRE\" dist/Andromeda.app"
echo "     xcrun notarytool submit ... (ver docs de Apple)"
