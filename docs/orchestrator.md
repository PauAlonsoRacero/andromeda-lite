# Andromeda — Orquestador Central

## Qué hace el orquestador

El orquestador es el cerebro de Andromeda. Para cada petición del usuario toma 6 decisiones en este orden:

1. **¿Hay especialistas disponibles?** Si no → 503 con instrucciones de configuración
2. **¿Qué hardware hay disponible ahora mismo?** Policy Engine consulta VRAM libre en tiempo real
3. **¿Qué especialistas usar?** Clasificador de intención (keywords o LLM)
4. **¿Qué estrategia aplicar?** Selección condicionada por tier de hardware
5. **¿Hay que degradar?** Si VRAM < umbral → simplificar automáticamente
6. **¿Qué registrar?** Trace completo de cada decisión para auditabilidad

## Flujo de decisión

```
prompt recibido
    │
    ▼
[Policy Engine] — ¿VRAM libre suficiente?
    │ SÍ: modo normal     NO: modo seguridad (single + generalist)
    ▼
[Clasificador] — keywords o LLM router
    │ → {specialists: [...], strategy: "...", confidence: 0.85}
    ▼
[Executor] — asyncio.gather() → paralelo real
    │ → [{specialist_id, content, latency_ms, success}, ...]
    ▼
[Merger] — aplica la estrategia
    │ → respuesta final (string)
    ▼
[Tracer] — guarda TraceRecord completo
```

## El clasificador híbrido

### Capa 1 — LLM Router (si orquestador configurado)

```yaml
# En specialists.yaml:
orchestrator:
  model_name: "phi3.5:3.8b"
  active: true
```

El orquestador clasifica el prompt con un timeout de **10 segundos**. Si supera el timeout o el JSON es inválido, cae automáticamente a keywords.

### Capa 2 — Keywords heurísticas (siempre disponible)

Sin necesidad de ningún modelo. Cuenta matches de términos técnicos por especialista y normaliza por longitud del prompt.

| Especialista | Keywords típicas |
|---|---|
| software-engineering | python, bug, function, code, debug, refactor, api, git... |
| it-ops | server, docker, nginx, network, firewall, ssh, kubernetes... |
| technical-writer | readme, documentation, doc, spec, adr, runbook... |
| verifier | verify, check, review, is correct, validate... |
| summarizer | summarize, resume, tldr, key points, extract... |

### Capa 3 — Fallback absoluto

Si ningún especialista hace match claro → `generalist + single`. Siempre funciona.

## Las 7 estrategias

| Estrategia | Cuándo usar | Tier mínimo |
|---|---|---|
| `single` | Una query clara, un dominio obvio | T1 |
| `latency_first` | Velocidad sobre calidad | T1 |
| `hardware_aware_fallback` | Safety net automático | T1 |
| `iterative_refine` | Código crítico, docs para producción | T2 |
| `verifier_pass` | Outputs que van a producción | T2 |
| `confidence_weighted` | Queries ambiguas o multidisciplinares | T3 |
| `quality_first` | Documentos importantes, análisis | T3 |

## Trazabilidad de decisiones

Cada petición genera un `TraceRecord` consultable en `/api/traces/{request_id}`:

```json
{
  "routing_reasoning": "Keywords detectadas: python, bug (score 0.72). T2 permite 2 especialistas. VRAM libre 11.2 GB > threshold 6 GB. Estrategia iterative_refine seleccionada como default T2.",
  "classifier_source": "keywords",
  "classifier_confidence": 0.72,
  "degraded": false,
  "spans": [
    {"name": "specialist:sw-engineering", "duration_ms": 9820},
    {"name": "specialist:verifier", "duration_ms": 9120},
    {"name": "merger:iterative_refine", "duration_ms": 3280}
  ]
}
```
