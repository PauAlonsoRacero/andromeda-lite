#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# download-models.sh — Descarga modelos base recomendados
# ══════════════════════════════════════════════════════════════════
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

echo ""
echo -e "${BLUE}✦ ANDROMEDA — Descarga de modelos${NC}"
echo "══════════════════════════════════════════════════════"

TIER=${1:-"t2"}

case "$TIER" in
  t1|T1)
    echo -e "${YELLOW}Tier 1 (8 GB VRAM) — modelos ligeros${NC}"
    MODELS=("phi3.5:3.8b" "llama3.2:3b")
    ;;
  t2|T2)
    echo -e "${GREEN}Tier 2 (16 GB VRAM) — modelos recomendados${NC}"
    MODELS=("phi3.5:3.8b" "qwen2.5-coder:7b" "mistral:7b" "llama3.2:3b")
    ;;
  t3|T3)
    echo "Tier 3 (24+ GB VRAM) — modelos de alta calidad"
    MODELS=("phi3.5:3.8b" "qwen2.5-coder:14b" "mistral:7b" "qwen2.5:14b")
    ;;
  *)
    echo "Uso: $0 [t1|t2|t3]"
    echo "  t1 — modelos para 8 GB VRAM"
    echo "  t2 — modelos para 16 GB VRAM (default)"
    echo "  t3 — modelos para 24+ GB VRAM"
    exit 1
    ;;
esac

echo ""
echo "Modelos a descargar: ${MODELS[*]}"
echo ""

for model in "${MODELS[@]}"; do
    echo -e "${BLUE}→ Descargando ${model}...${NC}"
    ollama pull "$model"
    echo -e "${GREEN}  ✓ ${model} listo${NC}"
    echo ""
done

echo "══════════════════════════════════════════════════════"
echo -e "${GREEN}Modelos descargados. Modelos disponibles:${NC}"
ollama list
echo ""
echo "Próximo paso: edita config/specialists.yaml y asigna los modelos."
echo ""
