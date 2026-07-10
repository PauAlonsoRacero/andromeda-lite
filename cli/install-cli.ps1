# ============================================================
#  ANDROMEDA CLI — Instalador para Windows
#  Crea el comando 'andromeda' disponible en PowerShell y CMD
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BinDir = "$env:USERPROFILE\.andromeda\bin"

Write-Host ""
Write-Host "  ✦ Instalando Andromeda CLI..." -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  [ERROR] Python no encontrado." -ForegroundColor Red
    Write-Host "  Instala Python desde https://python.org" -ForegroundColor Yellow
    Read-Host "  Enter para salir"; exit 1
}
$pyVersion = python --version 2>&1
Write-Host "  [OK] $pyVersion" -ForegroundColor Green

# 2. Crear directorio bin
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# 3. Copiar el CLI
Copy-Item "$ScriptDir\andromeda_cli.py" "$BinDir\andromeda_cli.py" -Force

# 4. Crear wrapper andromeda.cmd (funciona en CMD y PowerShell)
$wrapperCmd = @"
@echo off
python "$BinDir\andromeda_cli.py" %*
"@
$wrapperCmd | Set-Content "$BinDir\andromeda.cmd" -Encoding ASCII

# 5. Crear wrapper andromeda.ps1 (PowerShell nativo)
$wrapperPs1 = @"
#!/usr/bin/env pwsh
python "$BinDir\andromeda_cli.py" @args
"@
$wrapperPs1 | Set-Content "$BinDir\andromeda.ps1" -Encoding UTF8

# 6. Añadir al PATH si no está
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$BinDir", "User")
    Write-Host "  [OK] $BinDir añadido al PATH" -ForegroundColor Green
    Write-Host "  [!] Reinicia PowerShell para que el PATH se actualice" -ForegroundColor Yellow
} else {
    Write-Host "  [OK] PATH ya configurado" -ForegroundColor Green
}

# 7. Crear función de PowerShell para la sesión actual
$profileContent = @"

# Andromeda CLI
function andromeda { python "$BinDir\andromeda_cli.py" @args }
Set-Alias -Name and -Value andromeda
"@

# Añadir al perfil de PowerShell si no está ya
$profilePath = $PROFILE
if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Force -Path $profilePath | Out-Null
}
if (-not (Get-Content $profilePath -ErrorAction SilentlyContinue | Select-String "andromeda_cli")) {
    Add-Content $profilePath $profileContent
    Write-Host "  [OK] Función añadida al perfil de PowerShell" -ForegroundColor Green
}

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   ✦  Andromeda CLI instalado               ║" -ForegroundColor Green
Write-Host "  ║                                              ║" -ForegroundColor Green
Write-Host "  ║   Uso:                                      ║" -ForegroundColor Green
Write-Host "  ║     andromeda ""explica este error""          ║" -ForegroundColor Green
Write-Host "  ║     andromeda --shell                       ║" -ForegroundColor Green
Write-Host "  ║     andromeda --help                        ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  IMPORTANTE: Reinicia PowerShell para usar 'andromeda'" -ForegroundColor Yellow
Write-Host ""

# Probar la instalación en la sesión actual
Write-Host "  Probando la instalación..." -ForegroundColor Gray
$env:PATH += ";$BinDir"
try {
    $test = python "$BinDir\andromeda_cli.py" status --json 2>&1
    Write-Host "  [OK] CLI funciona correctamente" -ForegroundColor Green
} catch {
    Write-Host "  [!] CLI instalado pero Andromeda puede no estar corriendo" -ForegroundColor Yellow
}

Read-Host "  Presiona Enter para cerrar"
