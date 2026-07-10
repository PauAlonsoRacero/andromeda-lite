#!/bin/bash
# build_macos_app.command — Compila Andromeda.app standalone (ejecutar EN macOS)
# Doble clic en Finder o:  bash build_macos_app.command
set -e
cd "$(dirname "$0")"

echo "[0/5] Comprobando requisitos..."
command -v python3 >/dev/null || { echo "[X] python3 no encontrado. Instala Python 3.11+ (https://python.org o brew install python)"; exit 1; }
command -v npm >/dev/null || { echo "[X] npm no encontrado. Instala Node.js LTS (https://nodejs.org o brew install node)"; exit 1; }
echo "  $(python3 --version) | npm $(npm --version)"

# CRÍTICO: limpiar artefactos de builds anteriores. PyInstaller cachea en
# build/ y reutiliza objetos compilados; sin esto puede empaquetar código
# VIEJO aunque hayas actualizado los fuentes. Borrar garantiza un build limpio.
echo "[0.5/5] Limpiando builds anteriores (build/, dist/, frontend/dist)..."
rm -rf build dist frontend/dist
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "[1/5] Compilando frontend..."
(cd frontend && npm install --no-audit --no-fund && npx vite build)
# Comprobar que el frontend se generó de verdad; si no, abortar (mejor fallar
# aquí que empaquetar una interfaz vieja o vacía).
if [ ! -f frontend/dist/index.html ]; then
  echo "[X] El frontend no se compiló (no existe frontend/dist/index.html). Abortando."
  exit 1
fi
echo "  Frontend OK: $(find frontend/dist -name '*.js' | head -1)"

echo "[2/5] Creando entorno de build (.venv-build)..."
# venv: evita el bloqueo PEP 668 del Python de Homebrew y no ensucia el sistema
python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip --quiet

echo "[3/5] Instalando dependencias (solo wheels precompilados)..."
# --only-binary=:all: en los paquetes con código nativo evita compilar con Rust/C.
# Si tu versión de Python es muy nueva y algún wheel no existe aún, el segundo
# intento permite compilar solo ese paquete.
if ! python -m pip install --only-binary=pydantic-core,uvloop,httptools,watchfiles,psutil \
        --prefer-binary -r backend/requirements.txt pywebview pyinstaller; then
    echo "  Algún wheel no estaba disponible; reintentando sin restricción..."
    python -m pip install --prefer-binary -r backend/requirements.txt pywebview pyinstaller
fi

echo "[4/5] Empaquetando con PyInstaller (varios minutos)..."
python -m PyInstaller build_desktop.spec --noconfirm --clean
deactivate

echo "[5/5] Listo."
echo ""
echo "  Aplicación: dist/Andromeda.app"
echo "  Muévela a /Applications si quieres."
echo ""
echo "  ► Primera apertura (app sin firmar):"
echo "    - Clic derecho sobre Andromeda.app → Abrir → Abrir"
echo "    - Si macOS la bloquea igualmente, ejecuta:"
echo "        xattr -cr dist/Andromeda.app"
echo "      y vuelve a abrirla."
echo ""
echo "  ► Requisito: Ollama instalado (https://ollama.com/download)"
