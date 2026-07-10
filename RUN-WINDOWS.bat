@echo off
REM ============================================================
REM  RUN-WINDOWS.bat - Arranca Andromeda en tu PC sin Docker.
REM  Doble clic. Necesita Python 3.11+ y Node 18+ instalados.
REM  (No construye .exe; abre la app directamente. Para el .exe
REM   distribuible usa packaging\build_windows.ps1)
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo  == Andromeda - arranque local ==
echo.

REM --- Comprobar Python ---
where python >nul 2>nul
if errorlevel 1 (
  echo  [ERROR] No se encuentra Python. Instala Python 3.11+ desde python.org
  echo          y marca "Add python.exe to PATH" durante la instalacion.
  pause
  exit /b 1
)

REM --- Comprobar Node ---
where npm >nul 2>nul
if errorlevel 1 (
  echo  [ERROR] No se encuentra Node/npm. Instala Node 18+ desde nodejs.org
  pause
  exit /b 1
)

REM --- Construir el frontend si no existe ---
if not exist "frontend\dist\index.html" (
  echo  [1/3] Construyendo interfaz web por primera vez...
  pushd frontend
  call npm install
  call npm run build
  popd
) else (
  echo  [1/3] Interfaz web ya construida.
)

REM --- Instalar dependencias del backend ---
echo  [2/3] Instalando dependencias de Python...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r backend\requirements.txt "pywebview>=5.0" pythonnet

REM --- Arrancar la app ---
echo  [3/3] Abriendo Andromeda...
echo.
set PYTHONPATH=backend
python desktop.py

pause
