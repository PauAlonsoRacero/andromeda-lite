# ============================================================
#  ANDROMEDA SETUP — Instalador profesional v1.0
#  Windows 11 64-bit
#
#  Módulos instalados:
#    [CORE]      Docker Engine + Ollama + Andromeda
#    [METRICS]   MLOps dashboard (opcional)
#    [FINETUNE]  Entorno de entrenamiento (opcional, Fase 2)
#
#  Uso: clic derecho → Ejecutar como Administrador
# ============================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

# ── Configuración ─────────────────────────────────────────────────────────────
$ANDROMEDA_VERSION   = "1.0.0"
$INSTALL_DIR         = "$env:ProgramFiles\Andromeda"
$DATA_DIR            = "$env:APPDATA\Andromeda"
$DESKTOP             = [Environment]::GetFolderPath("Desktop")
$STARTUP             = [Environment]::GetFolderPath("CommonStartup")

$DOCKER_URL  = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
$OLLAMA_URL  = "https://ollama.com/download/OllamaSetup.exe"
$TEMP_DIR    = "$env:TEMP\AndromedaSetup"

# ── Colores ───────────────────────────────────────────────────────────────────
function Header {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Blue
    Write-Host "  ║   ✦  ANDROMEDA  Setup  v$ANDROMEDA_VERSION                 ║" -ForegroundColor Blue
    Write-Host "  ║      AI Orchestration Platform for Windows 11       ║" -ForegroundColor Blue
    Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Blue
    Write-Host ""
}

function OK($m)     { Write-Host "  ✓  $m" -ForegroundColor Green }
function STEP($n,$m){ Write-Host "`n  [$n] $m" -ForegroundColor Cyan }
function WARN($m)   { Write-Host "  ⚠  $m" -ForegroundColor Yellow }
function ERR($m)    { Write-Host "  ✗  $m" -ForegroundColor Red; Read-Host "  Presiona Enter para salir"; exit 1 }
function INFO($m)   { Write-Host "  →  $m" -ForegroundColor Gray }
function DL($m)     { Write-Host "     $m" -ForegroundColor DarkGray }

# ── Funciones de utilidad ─────────────────────────────────────────────────────
function Download($url, $dest, $label) {
    INFO "Descargando $label..."
    try {
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($url, $dest)
        OK "$label descargado"
    } catch {
        ERR "Error al descargar $label`: $_"
    }
}

function Is-Installed($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Wait-Docker {
    INFO "Esperando que Docker arranque..."
    $attempts = 0
    while ($attempts -lt 30) {
        try {
            $null = docker info 2>&1
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch {}
        Start-Sleep 5
        $attempts++
        Write-Host "     Esperando Docker... ($($attempts * 5)s)" -NoNewline
        Write-Host "`r" -NoNewline
    }
    return $false
}

# ══════════════════════════════════════════════════════════════════════════════
#  INICIO
# ══════════════════════════════════════════════════════════════════════════════
Header

Write-Host "  Este instalador configurará Andromeda AI en tu PC." -ForegroundColor White
Write-Host "  No necesitas saber qué es Docker ni Ollama." -ForegroundColor Gray
Write-Host ""
Write-Host "  Módulos disponibles:" -ForegroundColor White
Write-Host "    [1] CORE      — Chat con IAs + interfaz web (obligatorio)" -ForegroundColor Green
Write-Host "    [2] MÉTRICAS  — Dashboard de rendimiento y MLOps (recomendado)" -ForegroundColor Cyan
Write-Host "    [3] MODELOS   — Descarga automática de modelos de IA base" -ForegroundColor Yellow
Write-Host ""

$installMetrics = (Read-Host "  ¿Instalar módulo MÉTRICAS? [S/n]") -ne 'n'
$installModels  = (Read-Host "  ¿Descargar modelos de IA automáticamente? (~6GB) [S/n]") -ne 'n'

Write-Host ""
Write-Host "  Configuración seleccionada:" -ForegroundColor White
Write-Host "    Core:     SÍ (siempre)" -ForegroundColor Green
Write-Host "    Métricas: $(if($installMetrics){'SÍ'}else{'NO'})" -ForegroundColor $(if($installMetrics){'Green'}else{'Gray'})
Write-Host "    Modelos:  $(if($installModels){'SÍ (~6GB)'}else{'NO (lo harás luego)'})" -ForegroundColor $(if($installModels){'Yellow'}else{'Gray'})
Write-Host ""

$confirm = Read-Host "  ¿Continuar? [S/n]"
if ($confirm -eq 'n') { exit 0 }

# Crear directorios
New-Item -ItemType Directory -Force -Path $TEMP_DIR  | Out-Null
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $DATA_DIR   | Out-Null

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO CORE — PASO 1: Docker Desktop
# ══════════════════════════════════════════════════════════════════════════════
STEP "1/6" "Verificando Docker Desktop..."

$dockerInstalled = Is-Installed "docker"
$dockerRunning   = $false

if ($dockerInstalled) {
    OK "Docker ya está instalado"
    try {
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            OK "Docker está corriendo"
            $dockerRunning = $true
        } else {
            WARN "Docker instalado pero no corriendo — intentando arrancar..."
            Start-Process "Docker Desktop" -ErrorAction SilentlyContinue
            $dockerRunning = Wait-Docker
        }
    } catch {}
} else {
    INFO "Docker no encontrado — descargando Docker Desktop..."
    $dockerInstaller = "$TEMP_DIR\DockerDesktop.exe"
    Download $DOCKER_URL $dockerInstaller "Docker Desktop"

    INFO "Instalando Docker Desktop (puede tardar 2-3 minutos)..."
    $proc = Start-Process $dockerInstaller -ArgumentList "install --quiet --accept-license" -Wait -PassThru
    if ($proc.ExitCode -notin @(0, 1)) {
        WARN "El instalador de Docker terminó con código $($proc.ExitCode). Puede necesitar reinicio."
    }
    OK "Docker Desktop instalado"

    INFO "Arrancando Docker Desktop..."
    Start-Process "Docker Desktop"
    Start-Sleep 15
    $dockerRunning = Wait-Docker

    if (-not $dockerRunning) {
        WARN "Docker tardó en arrancar. Continúa de todas formas — puede necesitar reiniciar el PC."
        $dockerRunning = $true
    }
}

OK "Docker listo"

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO CORE — PASO 2: Ollama
# ══════════════════════════════════════════════════════════════════════════════
STEP "2/6" "Verificando Ollama..."

$ollamaInstalled = Is-Installed "ollama"

if ($ollamaInstalled) {
    OK "Ollama ya está instalado: $(ollama --version 2>&1 | Select-Object -First 1)"
} else {
    INFO "Ollama no encontrado — descargando..."
    $ollamaInstaller = "$TEMP_DIR\OllamaSetup.exe"
    Download $OLLAMA_URL $ollamaInstaller "Ollama"

    INFO "Instalando Ollama..."
    $proc = Start-Process $ollamaInstaller -ArgumentList "/SILENT" -Wait -PassThru
    OK "Ollama instalado"

    # Añadir Ollama al PATH de la sesión actual
    $env:PATH += ";$env:LOCALAPPDATA\Programs\Ollama"
}

OK "Ollama listo"

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO CORE — PASO 3: Copiar Andromeda
# ══════════════════════════════════════════════════════════════════════════════
STEP "3/6" "Instalando Andromeda en $INSTALL_DIR..."

# Copiar archivos del proyecto al directorio de instalación
$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Si el script está en installer/, subir un nivel
if ((Split-Path -Leaf $sourceDir) -eq "installer") {
    $sourceDir = Split-Path -Parent $sourceDir
}

INFO "Copiando archivos desde $sourceDir..."
$items = @("backend","frontend","config","docs","scripts","tests",
           "docker-compose.yml","docker-compose.dev.yml",".env.example",
           "Makefile","README.md","LICENSE","INICIO-RAPIDO.md")

foreach ($item in $items) {
    $src = Join-Path $sourceDir $item
    $dst = Join-Path $INSTALL_DIR $item
    if (Test-Path $src) {
        if (Test-Path -PathType Container $src) {
            Copy-Item $src $dst -Recurse -Force
        } else {
            Copy-Item $src $dst -Force
        }
    }
}

# Crear directorios de datos
New-Item -ItemType Directory -Force -Path "$INSTALL_DIR\data" | Out-Null
New-Item -ItemType Directory -Force -Path "$INSTALL_DIR\logs" | Out-Null

# Crear .env desde el ejemplo
if (-not (Test-Path "$INSTALL_DIR\.env")) {
    Copy-Item "$INSTALL_DIR\.env.example" "$INSTALL_DIR\.env"
    # Ajustar URL de Ollama para Docker
    (Get-Content "$INSTALL_DIR\.env") -replace "http://localhost:11434","http://ollama:11434" |
        Set-Content "$INSTALL_DIR\.env"
}

OK "Archivos de Andromeda copiados"

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO CORE — PASO 4: Construir contenedores Docker
# ══════════════════════════════════════════════════════════════════════════════
STEP "4/6" "Construyendo Andromeda (primera vez, tarda 3-5 minutos)..."

Set-Location $INSTALL_DIR

# Limpiar contenedores anteriores si existen
docker rm -f andromeda-ollama andromeda-backend andromeda-frontend 2>$null

INFO "Construyendo imágenes Docker..."
docker-compose pull   2>&1 | ForEach-Object { DL $_ }
docker-compose build  2>&1 | ForEach-Object { DL $_ }
OK "Imágenes construidas"

INFO "Arrancando Andromeda..."
docker-compose up -d 2>&1 | ForEach-Object { DL $_ }

# Esperar a que el backend responda
INFO "Esperando que el backend esté listo..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 3
    try {
        $r = Invoke-WebRequest "http://localhost:8000/api/health" -TimeoutSec 3 -UseBasicParsing -EA Stop
        if ($r.StatusCode -in @(200,503)) { $ready = $true; break }
    } catch {}
    Write-Host "     Esperando backend... ($($i*3)s)`r" -NoNewline
}

if ($ready) { OK "Andromeda corriendo en http://localhost" }
else { WARN "El backend tardó en arrancar — puede necesitar 1-2 minutos más" }

# ══════════════════════════════════════════════════════════════════════════════
#  MÓDULO MÉTRICAS — PASO 5 (opcional)
# ══════════════════════════════════════════════════════════════════════════════
STEP "5/6" "Módulo Métricas..."

if ($installMetrics) {
    INFO "El módulo Métricas ya está incluido en el Core (SQLite + MLOps)."
    INFO "Para activar MLflow avanzado, edita docker-compose.yml y descomenta el servicio mlflow."
    OK "Módulo Métricas: activo (básico)"
} else {
    INFO "Módulo Métricas omitido — puedes activarlo después desde la UI."
}

# ══════════════════════════════════════════════════════════════════════════════
#  MODELOS DE IA — PASO 6 (opcional)
# ══════════════════════════════════════════════════════════════════════════════
STEP "6/6" "Modelos de IA..."

if ($installModels) {
    INFO "Descargando modelos base (~6GB total). Esto puede tardar 10-20 minutos..."

    $models = @(
        @{name="phi3.5:3.8b";     desc="Orquestador + Verifier + Summarizer (~2GB)"},
        @{name="mistral:7b";      desc="Generalista + Technical Writer (~4GB)"},
        @{name="qwen2.5-coder:7b";desc="Software Engineering (~4GB)"}
    )

    foreach ($model in $models) {
        INFO "Descargando $($model.desc)..."
        & ollama pull $model.name
        OK "$($model.name) listo"
    }

    # Auto-configurar specialists.yaml con los modelos descargados
    INFO "Configurando especialistas automáticamente..."
    $yaml = Get-Content "$INSTALL_DIR\config\specialists.yaml" -Raw
    $yaml = $yaml -replace "(?m)(- id: software-engineering.*?model_name: )""PENDIENTE_CONFIGURAR""", "`${1}""qwen2.5-coder:7b"""
    $yaml = $yaml -replace "(?m)(- id: generalist.*?model_name: )""PENDIENTE_CONFIGURAR""", "`${1}""mistral:7b"""
    $yaml = $yaml -replace "(?m)(- id: verifier.*?model_name: )""PENDIENTE_CONFIGURAR""", "`${1}""phi3.5:3.8b"""
    $yaml = $yaml -replace "(?m)(- id: summarizer.*?model_name: )""PENDIENTE_CONFIGURAR""", "`${1}""phi3.5:3.8b"""
    $yaml = $yaml -replace "active: false", "active: true"
    $yaml | Set-Content "$INSTALL_DIR\config\specialists.yaml"

    # Reiniciar backend para que cargue la nueva configuración
    docker-compose -f "$INSTALL_DIR\docker-compose.yml" restart backend 2>$null
    OK "Especialistas configurados automáticamente"
} else {
    INFO "Modelos omitidos — configúralos desde la UI en la pestaña Modelos."
}

# ══════════════════════════════════════════════════════════════════════════════
#  ACCESO DIRECTO + AUTOSTART
# ══════════════════════════════════════════════════════════════════════════════

# Crear script de apertura rápida en el directorio de instalación
$openScript = @"
# Andromeda — Abrir
Set-Location "$INSTALL_DIR"
`$running = `$false
try {
    `$r = Invoke-WebRequest "http://localhost:8000/api/health" -TimeoutSec 3 -UseBasicParsing -EA Stop
    if (`$r.StatusCode -in @(200,503)) { `$running = `$true }
} catch {}

if (-not `$running) {
    docker-compose up -d 2>`$null
    Start-Sleep 20
}
Start-Process "http://localhost"
"@
$openScript | Set-Content "$INSTALL_DIR\Abrir-Andromeda.ps1" -Encoding UTF8

# Acceso directo en el Escritorio
$WshShell = New-Object -ComObject WScript.Shell
$sc = $WshShell.CreateShortcut("$DESKTOP\Andromeda.lnk")
$sc.TargetPath       = "powershell.exe"
$sc.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$INSTALL_DIR\Abrir-Andromeda.ps1`""
$sc.WorkingDirectory = $INSTALL_DIR
$sc.WindowStyle      = 7
$sc.Description      = "Andromeda AI Platform"
$sc.Save()
OK "Acceso directo creado en el Escritorio"

# Tarea de autostart con Windows
$TaskName   = "Andromeda AI Autostart"
$TaskAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -Command `"Set-Location '$INSTALL_DIR'; docker-compose up -d`"" `
    -WorkingDirectory $INSTALL_DIR
$TaskTrigger  = New-ScheduledTaskTrigger -AtLogon
$TaskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -EA SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $TaskTrigger `
    -Settings $TaskSettings -Description "Arranca Andromeda con Windows" | Out-Null
OK "Autostart configurado — Andromeda arrancará con Windows"

# ══════════════════════════════════════════════════════════════════════════════
#  RESUMEN FINAL
# ══════════════════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   ✦  ANDROMEDA instalado correctamente              ║" -ForegroundColor Green
Write-Host "  ║                                                      ║" -ForegroundColor Green
Write-Host "  ║   Instalado en: $INSTALL_DIR" -ForegroundColor Green
Write-Host "  ║                                                      ║" -ForegroundColor Green
Write-Host "  ║   Para abrir Andromeda:                             ║" -ForegroundColor Green
Write-Host "  ║     → Doble clic en 'Andromeda' del Escritorio     ║" -ForegroundColor Green
Write-Host "  ║                                                      ║" -ForegroundColor Green
Write-Host "  ║   URLs:                                             ║" -ForegroundColor Green
Write-Host "  ║     Chat:    http://localhost                       ║" -ForegroundColor Green
Write-Host "  ║     API:     http://localhost:8000/docs             ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# Abrir Andromeda ahora
$openNow = Read-Host "  ¿Abrir Andromeda ahora? [S/n]"
if ($openNow -ne 'n') {
    Start-Process "http://localhost"
}

# Limpiar archivos temporales
Remove-Item $TEMP_DIR -Recurse -Force -EA SilentlyContinue

Read-Host "  Presiona Enter para cerrar el instalador"
