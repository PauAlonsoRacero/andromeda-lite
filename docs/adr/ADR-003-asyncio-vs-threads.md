# ADR-003: asyncio.gather() sobre ThreadPoolExecutor para el executor

## Estado
Aceptado — Fase 0

## Contexto

El executor de Andromeda lanza N llamadas HTTP a Ollama simultáneamente (una por especialista). La pregunta es qué modelo de concurrencia usar.

Las llamadas a Ollama son **I/O-bound**: el tiempo de espera es la inferencia en GPU/CPU, no el procesamiento en la CPU del servidor. La diferencia entre I/O-bound y CPU-bound es crítica para elegir el modelo de concurrencia correcto.

**ThreadPoolExecutor:**
- Adecuado para tareas CPU-bound donde el GIL no es problema
- Para I/O-bound: cada thread bloquea esperando la respuesta HTTP, el GIL de Python limita que múltiples threads ejecuten código Python simultáneamente
- Overhead de creación y gestión de threads
- Con 3 especialistas: 3 threads, cada uno bloqueado esperando Ollama

**asyncio.gather():**
- Diseñado específicamente para I/O-bound concurrente
- Event loop único: lanza N coroutines, todas esperan I/O sin bloquear el loop
- Sin threads, sin GIL, sin overhead de context switching
- Con 3 especialistas: 3 coroutines en el mismo event loop, todas esperando Ollama en paralelo real

## Decisión

Usamos **asyncio.gather() con httpx.AsyncClient** para la ejecución paralela de especialistas.

```python
# Lanza los 3 especialistas simultáneamente
# Latencia total = max(latencia_spec1, latencia_spec2, latencia_spec3)
# No es la suma — es el más lento
results = await asyncio.gather(
    _call_specialist(spec1, prompt, config),
    _call_specialist(spec2, prompt, config),
    _call_specialist(spec3, prompt, config),
    return_exceptions=True   # si uno falla, los demás continúan
)
```

## Consecuencias

**Positivas:**
- Paralelismo real para I/O-bound sin limitaciones del GIL
- La latencia con N especialistas = latencia del más lento (no la suma)
- Sin overhead de threads — todo en el mismo event loop de FastAPI
- `return_exceptions=True` garantiza que un fallo individual no cancela el resto
- Integración natural con FastAPI (ya es async-first)

**Negativas:**
- Requiere que todo el stack sea async (httpx en lugar de requests)
- Más difícil de debuggear que código síncrono
- Si se mezcla código síncrono bloqueante, puede congelar el event loop

## Alternativas consideradas

**ThreadPoolExecutor**: descartado para I/O-bound. Funciona, pero el GIL limita el paralelismo real y añade overhead innecesario de gestión de threads.

**ProcessPoolExecutor**: descartado. El overhead de serialización entre procesos (pickle) para pasar los objetos de los especialistas es excesivo. Solo tiene sentido para CPU-bound pesado.

**Celery + Redis**: excesivo para fase 0. Añade infraestructura (Redis, workers) sin beneficio real. El paralelismo de asyncio es suficiente para hasta 3 especialistas simultáneos.
