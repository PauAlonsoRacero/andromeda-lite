# Andromeda Orquesta — Arquitectura del orquestador

Andromeda Orquesta es la capa de decisión que, para cada prompt, elige
**automáticamente** qué modelo(s) usar, de qué tamaño, y cómo combinar sus
respuestas — sin que el usuario tenga que configurar nada.

La filosofía: en vez de un único modelo gigante, usar el **módulo del tamaño
justo** para cada tarea, escalando la potencia solo cuando hace falta. Máxima
eficiencia de memoria manteniendo la calidad en cada tipo de tarea.

## Pipeline de decisión

```
prompt
  │
  ├─ 1. Clasificación      → dominio (código/razonamiento/redacción/datos/charla)
  │                          + ranking de especialistas
  │
  ├─ 2. Complejidad        → score [0,1] (longitud + señales + intención de output)
  │
  ├─ 3. Escalado de potencia → power_tier 1-4 = f(complejidad, dominio)
  │                            · cada dominio tiene peso y suelo propios
  │                            · razonar/programar exigen más que charlar
  │
  ├─ 4. Selección de modelo  → el más pequeño que cubre el tier pedido
  │                            (best_for_power), acotado por hardware/VRAM
  │
  ├─ 5. Nº de IAs            → 1 (simple) … 4 (complejo), por complejidad
  │
  └─ 6. Estrategia de fusión → single / synthesis / best_of_n / …
                               + IA de salida que unifica (si 2+ IAs)
```

## Componentes

| Componente | Archivo | Función |
|---|---|---|
| Orquestador | `core/orchestrator.py` | Construye el plan: dominio, complejidad, tier, especialistas, estrategia |
| Tiers de potencia | `models/schemas.py` → `best_for_power()` | Elige el modelo más pequeño suficiente |
| Registro | `specialists/registry.py` | Resuelve especialista → modelo concreto disponible |
| Confianza | `core/confidence.py` | Estima la calidad de la respuesta (heurística barata) |
| Fusión | `core/merger.py` | 14 estrategias para combinar respuestas |
| IA de salida | `core/output_ai.py` | Pasada final que unifica en una respuesta limpia |

## Escalado de potencia

`power_tier = f(complejidad, dominio)`:

- **Complejidad** [0,1]: longitud del prompt + señales de profundidad/técnicas +
  nº de preguntas + intención de output extenso.
- **Dominio**: cada uno con un peso (`reasoning` 1.35, `code` 1.20, `writing`
  0.95, `factual` 0.70, `conversation` 0.50) y un **suelo** (razonar/programar
  arrancan en tier 2).

Ejemplos reales (medidos en el banco de pruebas):

| Prompt | Dominio | Tier | Modelo (con 48GB VRAM) |
|---|---|---|---|
| "hola" | conversation | 1 | 3B |
| "¿capital de Francia?" | factual | 1 | 3B |
| "demuestra que √2 es irracional" | reasoning | 2 | 7-8B |
| "implementa un parser recursivo…" | code | 3 | 32B |
| "demuestra el teorema de Gödel…" | reasoning | 3 | 32B |

## Evaluación

El enrutamiento se mide con un banco de pruebas (`eval/`):

```bash
python eval/eval_routing.py                              # entrenamiento
python eval/eval_routing.py --dataset eval/routing_holdout.jsonl   # validación
```

Métricas actuales:

| Conjunto | Dominio | Especialista | Tier en rango |
|---|---|---|---|
| Entrenamiento (51) | 100% | 100% | 100% |
| Validación (24, casos nuevos) | 96% | 96% | 96% |

`GET /api/orchestra/eval` expone estas métricas en vivo.
`POST /api/orchestra/explain` explica la decisión para un prompt dado sin ejecutarlo.

## Límites honestos

- Esto **no iguala a un modelo de 600B en general**. Acerca mucho en tareas
  concretas donde un modelo especializado del tamaño justo rinde como uno grande,
  gastando una fracción de la memoria.
- La confianza es una heurística barata, no un juez perfecto.
- Los pesos por dominio son un punto de partida razonable, afinado con el banco
  de pruebas; se seguirán ajustando con más datos.
