#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# bootstrap.sh — Setup inicial de Andromeda
# Ejecutar una sola vez al clonar el repositorio
# ══════════════════════════════════════════════════════════════════
set -e

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERR]${NC}  $1"; exit 1; }

echo ""
echo -e "${BLUE}✦ ANDROMEDA Bootstrap${NC}"
echo "══════════════════════════════════════════════════════"
echo ""

# ── Verificar dependencias ────────────────────────────────────────
info "Verificando dependencias..."

command -v docker >/dev/null 2>&1 || error "Docker no encontrado. Instala Docker Desktop: https://docker.com/products/docker-desktop/"
command -v ollama >/dev/null 2>&1 || error "Ollama no encontrado. Instala: https://ollama.com"
command -v git    >/dev/null 2>&1 || error "Git no encontrado."

success "Docker: $(docker --version | head -1)"
success "Ollama: $(ollama --version 2>&1 | head -1)"
success "Git: $(git --version)"

# ── Crear .env si no existe ───────────────────────────────────────
if [ ! -f ".env" ]; then
    info "Creando .env desde .env.example..."
    cp .env.example .env
    success ".env creado"
else
    warn ".env ya existe, no se sobreescribe"
fi

# ── Crear directorios de datos ────────────────────────────────────
info "Creando directorios de datos..."
mkdir -p data logs
success "Directorios: data/ logs/"

# ── Verificar Docker está corriendo ──────────────────────────────
info "Verificando Docker..."
docker ps >/dev/null 2>&1 || error "Docker no está corriendo. Arranca Docker Desktop."
success "Docker está corriendo"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Bootstrap completado.${NC}"
echo ""
echo "  Próximos pasos:"
echo "  1. Descarga modelos:       bash scripts/download-models.sh"
echo "  2. Configura especialistas: edita config/specialists.yaml"
echo "  3. Arranca:                docker-compose up -d"
echo "  4. Abre:                   http://localhost"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo ""
