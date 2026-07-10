#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# demo.sh — Prepara y lanza la demo de Andromeda
# ══════════════════════════════════════════════════════════════════
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${BLUE}✦ ANDROMEDA Demo Setup${NC}"
echo "══════════════════════════════════════════════════════"

# 1. Verificar que los servicios están corriendo
echo -e "${BLUE}[1/4] Verificando servicios...${NC}"
if ! docker-compose ps | grep -q "Up"; then
    echo "  Servicios no corriendo. Arrancando..."
    docker-compose up -d
    echo "  Esperando 20 segundos para que los servicios arranquen..."
    sleep 20
fi

# 2. Verificar health
echo -e "${BLUE}[2/4] Verificando health...${NC}"
HEALTH=$(curl -s http://localhost:8000/api/health 2>/dev/null || echo '{"status":"down"}')
STATUS=$(echo $HEALTH | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','down'))" 2>/dev/null || echo "down")

if [ "$STATUS" = "down" ]; then
    echo -e "${RED}  ERROR: Sistema no disponible. Revisa: docker-compose logs backend${NC}"
    exit 1
fi
echo -e "${GREEN}  Sistema: $STATUS${NC}"

# 3. Verificar especialistas
ACTIVE=$(echo $HEALTH | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('specialists',{}).get('active',0))" 2>/dev/null || echo 0)
if [ "$ACTIVE" = "0" ]; then
    echo -e "${YELLOW}  AVISO: Sin especialistas activos. Configura config/specialists.yaml${NC}"
else
    echo -e "${GREEN}  Especialistas activos: $ACTIVE${NC}"
fi

# 4. Warmup de modelos (petición de 1 token para precargar en memoria)
echo -e "${BLUE}[3/4] Warmup de modelos activos...${NC}"
WARMUP=$(curl -s -X GET http://localhost:8000/api/models/active 2>/dev/null)
MODELS=$(echo $WARMUP | python3 -c "
import sys,json
d=json.load(sys.stdin)
specs=d.get('specialists',[])
print(' '.join(s['model_name'] for s in specs if s['model_name'] != 'PENDIENTE_CONFIGURAR'))
" 2>/dev/null || echo "")

if [ -n "$MODELS" ]; then
    for model in $MODELS; do
        echo "  Calentando $model..."
        ollama run "$model" "." >/dev/null 2>&1 || true
    done
    echo -e "${GREEN}  Warmup completado${NC}"
fi

# 5. Abrir browser
echo -e "${BLUE}[4/4] Abriendo UI...${NC}"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Demo lista.${NC}"
echo ""
echo "  UI:       http://localhost"
echo "  API Docs: http://localhost:8000/docs"
echo "  Health:   http://localhost:8000/api/health"
echo "  MLOps:    http://localhost:8000/api/mlops/summary"
echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
echo ""

# Abrir browser si es macOS o Windows (WSL)
if command -v open >/dev/null 2>&1; then
    open http://localhost
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost
fi
