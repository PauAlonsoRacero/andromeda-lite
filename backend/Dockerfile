# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Dependencias del sistema para psutil y compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero — cachea esta capa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copiar dependencias del build stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar código fuente
COPY . .

# Crear directorios necesarios
RUN mkdir -p data logs

EXPOSE 8000

ENV ANDROMEDA_ENVIRONMENT=production
ENV ANDROMEDA_PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)"

# Arrancar con factory pattern — obligatorio para el lifespan de FastAPI
CMD ["uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
