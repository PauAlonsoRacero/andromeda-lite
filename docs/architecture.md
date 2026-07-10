# Andromeda — Arquitectura

## Diagrama de capas

```
┌──────────────────────────────────────────────────────────────────┐
│                      ANDROMEDA PLATFORM v1.0                      │
│                                                                    │
│  ┌─────────────────┐  SSE/HTTP   ┌────────────────────────────┐  │
│  │   SolidJS UI    │◄───────────►│  FastAPI + Uvicorn (ASGI)  │  │
│  │   Port 5173     │             │  Port 8000                  │  │
│  └─────────────────┘             └──────────────┬─────────────┘  │
│                                                  │                 │
│                             ┌────────────────────▼─────────────┐ │
│                             │       ORCHESTRATOR CORE           │ │
│                             │  Classifier → Policy Engine       │ │
│                             │  Router → Executor → Merger       │ │
│                             └──────────┬──────────┬────────────┘ │
│                          ┌─────────────┘          └────────────┐ │
│                     asyncio.gather()              asyncio.gather │ │
│                    ┌──────┴──────┐             ┌───────┴──────┐  │
│                    │   spec 1    │             │   spec 2     │  │
│                    └──────┬──────┘             └───────┬──────┘  │
│                           └──────────┬──────────────────┘        │
│                                      │                            │
│                         ┌────────────▼──────────────┐            │
│                         │   Ollama :11434             │            │
│                         │   GGUF · CUDA/Metal/ROCm   │            │
│                         └───────────────────────────┘            │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  OBSERVABILITY: OpenTelemetry → SQLite (data/traces.db)    │  │
│  │  MLOPS:         MLOpsTracker → SQLite (data/mlops_runs.db) │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Módulos del backend

### `hardware/`
- **`detector.py`**: Detecta CPU, RAM, VRAM, aceleración (CUDA/ROCm/Metal/CPU). Nunca lanza excepción.
- **`policy.py`**: Traduce el hardware en comportamiento. `get_policy()` para la política base del tier. `derive_runtime_policy()` para la política dinámica de cada request.

### `specialists/`
- **`profiles.py`**: Los 6 especialistas hardcoded con sus system prompts. Fuente de verdad.
- **`registry.py`**: Gestión del catálogo con 3 capas: profiles.py → specialists.yaml → runtime override.

### `core/`
- **`classifier.py`**: LLM router (timeout 10s) + keywords fallback + fallback absoluto.
- **`executor.py`**: `asyncio.gather()` para paralelismo real. Manejo de errores por especialista.
- **`merger.py`**: 7 estrategias de fusión. Fallbacks internos para cada una.
- **`router.py`**: Pipeline end-to-end. Coordina todos los componentes. El `finally` garantiza que el trace siempre se guarda.

### `observability/`
- **`store.py`**: SQLite async con WAL mode. Rotación automática de traces antiguos.
- **`tracer.py`**: Árbol de spans por request. `build_routing_reasoning()` para explicaciones legibles.
- **`metrics.py`**: Ventana deslizante de 1000 peticiones. P50/P95/P99 calculados on-demand.

### `mlops/`
- **`tracker.py`**: Tracking de experimentos en SQLite. Model registry con métricas por modelo. MLflow como backend opcional cuando se instala.

## Decisiones de diseño clave

Ver los ADRs en `docs/adr/`:

| Decisión | ADR |
|---|---|
| FastAPI sobre Flask | ADR-001 |
| SolidJS sobre React | ADR-002 |
| asyncio.gather sobre ThreadPoolExecutor | ADR-003 |
| Definición de los 4 tiers de hardware | ADR-004 |

## Flujo de datos de un request

```
POST /api/chat
  │
  ├─ Validación Pydantic (ChatRequest)
  ├─ Iniciar span + MLOps run
  ├─ get_eligible_specialists(tier)
  ├─ derive_runtime_policy(hardware, vram_actual)
  ├─ classify_prompt(LLM o keywords)
  ├─ asyncio.gather([specialist_1, specialist_2])
  │     └─ httpx.AsyncClient → POST ollama:11434/api/chat
  ├─ merge_responses(strategy)
  ├─ Construir ChatResponse
  └─ finally: save(TraceRecord) + end_run(MLOps)
```
