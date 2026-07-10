# Andromeda — Runbook Operativo

## Arranque diario

```bash
cd andromeda
docker-compose up -d
sleep 15
curl http://localhost:8000/api/health
# Abrir http://localhost
```

## Parada segura

```bash
docker-compose down
# Los traces SQLite persisten en el volumen Docker
# Los modelos de Ollama persisten en el volumen ollama_models
```

## Troubleshooting rápido

| Síntoma | Diagnóstico | Solución |
|---|---|---|
| `status: down` | Ollama no responde | `docker-compose logs ollama` → ver si arrancó |
| `status: degraded` + 0 especialistas | Ningún modelo configurado | Editar `config/specialists.yaml` → reiniciar backend |
| Chat timeout (>120s) | Modelo demasiado grande | Usar modelo más pequeño en `specialists.yaml` |
| OOM en Ollama | VRAM insuficiente | Policy Engine debería haberlo prevenido; revisar `safe_vram_threshold_gb` en `hardware_policies.yaml` |
| Frontend en blanco | Backend caído | `docker-compose restart backend` |
| "Modelo no encontrado" | No descargado en Ollama | `ollama pull nombre-del-modelo` |
| Traces no aparecen | SQLite corrupto | `docker-compose exec backend python3 -c "from app.observability.store import TraceStore; import asyncio; asyncio.run(TraceStore('data/traces.db').init())"` |

## Logs en tiempo real

```bash
docker-compose logs -f backend    # logs del orquestador
docker-compose logs -f ollama     # logs del servidor de modelos
docker-compose logs -f frontend   # logs de nginx
```

## Cambiar modelo de un especialista SIN reiniciar

```bash
# Via API (cambio en memoria, se pierde al reiniciar):
curl -X PUT http://localhost:8000/api/models/software-engineering \
  -H "Content-Type: application/json" \
  -d '{"model_name": "qwen2.5-coder:14b", "active": true}'

# Para persistir: editar config/specialists.yaml y reiniciar backend
docker-compose restart backend
```

## Verificar que un modelo funciona antes de activarlo

```bash
curl -X POST http://localhost:8000/api/models/software-engineering/test
# Retorna: {success, response, latency_ms}
```

## Consultar el último trace

```bash
# Últimos 5 traces
curl http://localhost:8000/api/traces?limit=5 | python3 -m json.tool

# Trace completo de un request específico
curl http://localhost:8000/api/traces/{request_id} | python3 -m json.tool
```

## Métricas operativas

```bash
# Métricas en tiempo real
curl http://localhost:8000/api/traces/metrics | python3 -m json.tool

# Resumen MLOps (runs, success rate, model registry)
curl http://localhost:8000/api/mlops/summary | python3 -m json.tool

# Comparar modelos para un especialista
curl http://localhost:8000/api/mlops/models/software-engineering | python3 -m json.tool
```

## Activar MLflow (Fase 1)

```bash
# 1. Descomentar en docker-compose.yml el servicio mlflow
# 2. Añadir en .env:
echo "ANDROMEDA_MLFLOW_ENABLED=true" >> .env
echo "ANDROMEDA_MLFLOW_TRACKING_URI=http://mlflow:5001" >> .env
# 3. Reiniciar
docker-compose up -d
# 4. Abrir MLflow UI: http://localhost:5001
```

## Backup de traces

```bash
# Los traces están en el volumen Docker andromeda_data
# Para exportar a archivo local:
docker-compose exec backend python3 -c "
import json, asyncio
from app.observability.store import TraceStore
store = TraceStore('data/traces.db')
traces = asyncio.run(store.get_recent(200))
print(json.dumps(traces, indent=2))
" > backup_traces_$(date +%Y%m%d).json
```
