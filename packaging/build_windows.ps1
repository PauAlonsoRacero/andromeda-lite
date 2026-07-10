# build_windows.ps1 — Construye Andromeda para Windows 11 (.exe + instalador).
# Requisitos: Python 3.11+, Node 18+, y ejecutarlo EN Windows.
# Uso:  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Lecciones aprendidas (NO borrar):
#  - PyInstaller CACHEA build\ y dist\: hay que limpiarlos o compila binarios viejos.
#  - El frontend DEBE compilarse antes; si falta frontend\dist\index.html, abortar.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "==> [pre] Verificando requisitos (Python, Node)" -ForegroundColor Cyan
foreach ($cmd in @("python", "node", "npm")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "Falta '$cmd'. Instala Python 3.11+ (python.org) y Node 18+ (nodejs.org) y reintenta."
        exit 1
    }
}
$pyver = (python --version)
Write-Host "    $pyver / Node $(node --version)" -ForegroundColor DarkGray

Write-Host "==> [0/5] Limpiando cachés de compilaciones anteriores" -ForegroundColor Cyan
# Igual que en macOS: sin esto, PyInstaller reutiliza objetos viejos.
Remove-Item -Recurse -Force build, dist, frontend\dist -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "==> [1/5] Frontend (Vite build)" -ForegroundColor Cyan
Push-Location frontend
npm install
npm run build
Pop-Location
if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Error "ABORTADO: frontend\dist\index.html no existe. El build del frontend falló."
    exit 1
}

Write-Host "==> [2/5] Dependencias backend + PyInstaller + pywebview (WebView2)" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
# pywebview en Windows necesita pythonnet (clr) para el motor EdgeChromium/WebView2.
python -m pip install pyinstaller "pywebview>=5.0" pythonnet

Write-Host "==> [3/5] Empaquetado con PyInstaller (--clean)" -ForegroundColor Cyan
pyinstaller build_desktop.spec --noconfirm --clean
if (-not (Test-Path "dist\Andromeda\Andromeda.exe")) {
    Write-Error "ABORTADO: dist\Andromeda\Andromeda.exe no se generó."
    exit 1
}

if (-not (Test-Path "packaging\redist\OllamaSetup.exe")) {
    Write-Host "    Aviso: packaging\redist\OllamaSetup.exe no esta. El instalador se creara" -ForegroundColor Yellow
    Write-Host "    SIN Ollama incluido (Andromeda guiara al usuario al abrirse)." -ForegroundColor Yellow
    Write-Host "    Para incluirlo: descarga https://ollama.com/download/OllamaSetup.exe a packaging\redist\" -ForegroundColor Yellow
}
Write-Host "==> [4/5] Instalador con Inno Setup" -ForegroundColor Cyan
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc "packaging\installer.iss"
    Write-Host "    Instalador creado en dist\installer\" -ForegroundColor Green
} else {
    Write-Host "    Inno Setup no encontrado. Instálalo de https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
    Write-Host "    Luego ejecuta:  iscc packaging\installer.iss" -ForegroundColor Yellow
}

Write-Host "==> [5/5] Listo." -ForegroundColor Green
Write-Host "    App suelta:  dist\Andromeda\Andromeda.exe"
Write-Host "    Instalador:  dist\installer\Andromeda-Setup-*.exe (si Inno Setup estaba instalado)"
