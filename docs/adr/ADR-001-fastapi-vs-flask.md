# ADR-001: FastAPI sobre Flask para el backend de Andromeda

## Estado
Aceptado — Fase 0

## Contexto

Andromeda necesita un backend que soporte tres capacidades técnicas no negociables:

1. **SSE nativo** para streaming token a token desde Ollama hasta el cliente
2. **asyncio** para lanzar N especialistas en paralelo sin bloquear el event loop
3. **Pydantic v2** para validación y serialización de todos los schemas del sistema

Flask es un framework WSGI (síncrono). Para añadir streaming SSE o concurrencia async en Flask se necesitan extensiones externas (Flask-SSE, gevent, eventlet) que parchean el runtime de Python de forma no estándar y generan comportamientos impredecibles bajo carga.

FastAPI es un framework ASGI (async-first). SSE, WebSockets y asyncio son capacidades nativas, no extensiones.

## Decisión

Usamos **FastAPI 0.115+ con Uvicorn** como ASGI server.

## Consecuencias

**Positivas:**
- `StreamingResponse` para SSE sin ninguna dependencia adicional
- `asyncio.gather()` para paralelismo real de especialistas (I/O-bound)
- Pydantic v2 integrado — validación automática de todos los endpoints
- OpenAPI automático en `/docs` — la API se documenta sola
- 15.000–20.000 req/s vs 2.000–3.000 de Flask en benchmarks de I/O
- Ecosistema de facto para backends de IA en 2025

**Negativas:**
- Ecosistema de plugins más pequeño que Flask
- Curva de aprendizaje de async/await para developers sin experiencia async

## Alternativas consideradas

**Flask + gevent**: descartado. gevent parchea el event loop de Python con monkey-patching, lo que genera bugs intermitentes difíciles de diagnosticar. El SSE requiere una extensión (Flask-SSE) que añade Redis como dependencia. No es una solución limpia.

**Starlette directo**: descartado. FastAPI es Starlette con las capas de validación, routing y documentación que necesitamos de todas formas. Usar Starlette directamente significaría reimplementar lo que FastAPI ya da.

**Django + ASGI**: descartado. Django añade ORM, admin, auth y capa de configuración que no necesitamos. Es excesivo para un backend de orquestación de IA.
