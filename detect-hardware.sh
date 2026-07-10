#!/usr/bin/env bash
# detect-hardware.sh — Detecta el hardware del HOST y lo escribe en .env
# para que el contenedor Docker conozca la GPU/RAM real (no la ve por sí mismo).
# Uso:  bash detect-hardware.sh   (antes de 'docker compose up')
set -e

ENV_FILE=".env"
OS="$(uname -s)"
GPU=""
VRAM_GB="0"
RAM_GB="0"
CPU=""

if [ "$OS" = "Darwin" ]; then
    # macOS — Apple Silicon usa memoria unificada
    CPU="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon')"
    RAM_BYTES="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
    RAM_GB="$(echo "scale=0; $RAM_BYTES/1073741824" | bc 2>/dev/null || echo 8)"
    CHIP="$(system_profiler SPDisplaysDataType 2>/dev/null | grep -m1 'Chipset Model' | sed 's/.*: //' || echo '')"
    if [ -n "$CHIP" ]; then
        GPU="$CHIP"
    else
        GPU="Apple GPU"
    fi
    # Memoria unificada: casi toda la RAM es usable como VRAM (reservamos ~25%)
    if [ "$RAM_GB" -ge 32 ]; then
        VRAM_GB="$((RAM_GB - 6))"
    elif [ "$RAM_GB" -ge 16 ]; then
        VRAM_GB="$((RAM_GB - 4))"
    else
        VRAM_GB="$((RAM_GB / 2))"
    fi
    HOST_OS="macOS"
elif [ "$OS" = "Linux" ]; then
    CPU="$(grep -m1 'model name' /proc/cpuinfo | sed 's/.*: //' || echo 'CPU')"
    RAM_KB="$(grep MemTotal /proc/meminfo | awk '{print $2}')"
    RAM_GB="$((RAM_KB / 1048576))"
    HOST_OS="Linux"
    # GPU NVIDIA
    if command -v nvidia-smi >/dev/null 2>&1; then
        GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
        VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)"
        VRAM_GB="$((VRAM_MB / 1024))"
    fi
fi

# Escribir/actualizar el .env (sin duplicar)
touch "$ENV_FILE"
sed -i.bak '/^ANDROMEDA_HOST_/d' "$ENV_FILE" 2>/dev/null || true
{
    echo "ANDROMEDA_HOST_OS=$HOST_OS"
    echo "ANDROMEDA_HOST_CPU=$CPU"
    echo "ANDROMEDA_HOST_RAM_GB=$RAM_GB"
    echo "ANDROMEDA_HOST_GPU=$GPU"
    echo "ANDROMEDA_HOST_VRAM_GB=$VRAM_GB"
} >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Hardware detectado y escrito en $ENV_FILE:"
echo "  OS:   $HOST_OS"
echo "  CPU:  $CPU"
echo "  RAM:  ${RAM_GB} GB"
echo "  GPU:  $GPU"
echo "  VRAM: ${VRAM_GB} GB (estimada para memoria unificada en Mac)"
