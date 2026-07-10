"""
executor.py — Motor de ejecución de especialistas de Andromeda.

Lanza las llamadas a Ollama en paralelo usando asyncio.gather().

Por qué asyncio y no threads:
  - Las llamadas a Ollama son I/O-bound (esperar respuesta de GPU/CPU)
  - asyncio.gather() lanza N coroutines simultáneamente en el mismo event loop
  - Con threads, el GIL de Python limita el paralelismo real en I/O
  - httpx.AsyncClient es el cliente HTTP async estándar en 2025

Modos de ejecución:
  - PARALELO (default): todos los especialistas se lanzan a la vez
    Latencia = max(latencia_spec1, latencia_spec2, ...) — no suma
  - SERIE (strategy="chain"): el output de cada especialista
    se pasa como contexto al siguiente — latencia suma

Uso:
    results = await execute_specialists(
        specialists=[sw_eng_profile, verifier_profile],
        prompt="Fix this bug...",
        strategy="iterative_refine",
        config={"temperature": 0.7, "max_tokens": 2048, "timeout": 120},
    )
    # results = [{specialist_id, content, latency_ms, success, ...}, ...]
"""

import asyncio
import logging
import time

import httpx

from app.models.schemas import SpecialistProfile
from app.specialists.identity import with_identity

logger = logging.getLogger("andromeda.executor")


async def execute_specialists(
    specialists: list[SpecialistProfile],
    prompt: str,
    strategy: str,
    config: dict,
) -> list[dict]:
    """
    Ejecuta los especialistas y retorna sus respuestas.

    Args:
        specialists: Lista de especialistas a ejecutar
        prompt: Texto del usuario
        strategy: Estrategia de ejecución (determina si paralelo o serie)
        config: Configuración de inferencia:
                  - ollama_url: URL base de Ollama
                  - temperature: temperatura de generación
                  - max_tokens: tokens máximos
                  - timeout: timeout en segundos

    Returns:
        Lista de dicts con el resultado de cada especialista.
        Cada resultado:
          {specialist_id, model_name, content, latency_ms, success, error}
        Un especialista que falla tiene success=False y content="".
        NUNCA lanza excepción — los errores individuales se capturan.
    """
    if not specialists:
        logger.warning("execute_specialists llamado sin especialistas. Retornando vacío.")
        return []

    # ── Ejecución en SERIE (solo para strategy="chain") ──────────────────────
    if strategy == "chain":
        return await _execute_chain(specialists, prompt, config)

    # ── Ejecución en PARALELO (default para todas las demás estrategias) ─────
    return await _execute_parallel(specialists, prompt, config)


async def _execute_parallel(
    specialists: list[SpecialistProfile],
    prompt: str,
    config: dict,
) -> list[dict]:
    """
    Ejecuta todos los especialistas simultáneamente con asyncio.gather.

    asyncio.gather() lanza todas las coroutines a la vez y espera
    a que TODAS terminen. La latencia total es la del más lento, no la suma.

    return_exceptions=True asegura que si un especialista falla,
    los demás continúan — no se cancela todo.
    """
    logger.debug(f"Ejecutando {len(specialists)} especialistas en PARALELO")

    # Crear una tarea por especialista
    tasks = [
        _call_specialist(specialist, prompt, config)
        for specialist in specialists
    ]

    # Lanzar todas a la vez — paralelismo real en I/O
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Procesar los resultados — convertir excepciones en errores estructurados
    results = []
    for specialist, result in zip(specialists, raw_results):
        if isinstance(result, Exception):
            # El especialista falló — registrar el error pero no crashear
            logger.error(
                f"Especialista '{specialist.id}' falló con excepción: {result}"
            )
            results.append({
                "specialist_id": specialist.id,
                "model_name": specialist.model_name,
                "content": "",
                "latency_ms": 0.0,
                "success": False,
                "error": str(result),
            })
        else:
            results.append(result)

    successful = sum(1 for r in results if r["success"])
    logger.info(
        f"Ejecución paralela completada: {successful}/{len(specialists)} exitosos. "
        f"Latencias: {[r['specialist_id']+'='+str(round(r['latency_ms']))+'ms' for r in results]}"
    )

    return results


async def _execute_chain(
    specialists: list[SpecialistProfile],
    prompt: str,
    config: dict,
) -> list[dict]:
    """
    Ejecuta los especialistas en SERIE, pasando el output de cada uno
    como contexto adicional al siguiente.

    Útil para pipelines donde el segundo especialista necesita
    ver el output del primero para mejorar o verificar.

    Estructura del prompt encadenado:
      Prompt original + "Contexto del especialista anterior: {output_anterior}"
    """
    logger.debug(f"Ejecutando {len(specialists)} especialistas en CADENA (serie)")

    results = []
    accumulated_context = ""

    for i, specialist in enumerate(specialists):
        # Si no es el primer especialista, incluir el output del anterior como contexto
        if accumulated_context:
            chained_prompt = (
                f"{prompt}\n\n"
                f"--- Contexto del análisis anterior ---\n"
                f"{accumulated_context}\n"
                f"--- Fin del contexto ---\n\n"
                f"Teniendo en cuenta el análisis anterior, responde al prompt original."
            )
        else:
            chained_prompt = prompt

        result = await _call_specialist(specialist, chained_prompt, config)
        results.append(result)

        # Acumular el contexto para el siguiente especialista
        if result["success"] and result["content"]:
            accumulated_context = (
                f"[{specialist.name}]: {result['content'][:1000]}"  # Limitar para no exceder contexto
            )
            if len(result["content"]) > 1000:
                accumulated_context += "... [truncado]"

        logger.debug(f"Cadena paso {i+1}/{len(specialists)}: {specialist.id} → success={result['success']}")

    return results


async def _call_specialist(
    specialist: SpecialistProfile,
    prompt: str,
    config: dict,
) -> dict:
    """
    Hace una llamada HTTP async a Ollama para un especialista concreto.

    Esta función NUNCA lanza excepción. Si algo falla, retorna
    un resultado con success=False y el mensaje de error.

    Args:
        specialist: El especialista a ejecutar
        prompt: Texto a procesar
        config: Configuración (ollama_url, temperature, max_tokens, timeout)

    Returns:
        {specialist_id, model_name, content, latency_ms, success, error}
    """
    t_start = time.perf_counter()

    ollama_url = config.get("ollama_url", "http://localhost:11434")
    temperature = config.get("temperature", 0.7)
    max_tokens = config.get("max_tokens", 2048)
    timeout = config.get("timeout", 120)

    # Si hay herramientas MCP conectadas, usar el ciclo de tool-calling: el
    # modelo puede pedir herramientas (crear archivos, leer web, etc.) y se
    # ejecutan de verdad. Solo si hay al menos una herramienta disponible.
    mcp_manager = config.get("mcp_manager")
    from app.core.model_catalog import supports_tools as _supports_tools
    if mcp_manager is not None and _supports_tools(specialist.model_name):
        try:
            _tools = mcp_manager.tools
            if _tools:
                from app.mcp.executor import MCPExecutor
                _execu = MCPExecutor(mcp_manager, metrics=config.get("metrics"))
                final_text, tool_log = await _execu.run_with_tools(
                    prompt=prompt,
                    model_name=specialist.model_name,
                    system_prompt=with_identity(specialist.system_prompt, specialist.id, specialist.model_name),
                    ollama_url=ollama_url,
                )
                return {
                    "specialist_id": specialist.id,
                    "model_name": specialist.model_name,
                    "content": final_text,
                    "latency_ms": (time.perf_counter() - t_start) * 1000,
                    "success": True,
                    "error": None,
                    "tool_calls": tool_log,
                }
        except Exception as exc:
            logger.warning(f"Tool-calling MCP falló, usando chat normal: {exc}")

    # Construir el payload para la API de Ollama
    payload = {
        "model": specialist.model_name,
        "messages": [
            {
                "role": "system",
                # El system prompt del especialista + identidad de Andromeda
                "content": with_identity(specialist.system_prompt, specialist.id, specialist.model_name),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "options": {
            "temperature": temperature,
            # num_predict es el nombre de Ollama para max_tokens
            "num_predict": max_tokens,
        },
        # stream=False: esperamos la respuesta completa
        # (staircase streaming se implementa en streaming.py en Fase 1)
        "stream": False,
    }

    try:
        # Retry con backoff ante caídas transitorias de conexión: Ollama puede
        # estar arrancando o reiniciándose. Reintentamos hasta 3 veces (0.5s,
        # 1s, 2s) SOLO en errores de conexión; otros errores no se reintentan.
        _max_retries = 3
        _last_connect_err = None
        for _attempt in range(_max_retries):
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    response = await client.post(
                        f"{ollama_url}/api/chat",
                        json=payload,
                        timeout=timeout,
                    )
                    response.raise_for_status()
                _last_connect_err = None
                break
            except httpx.ConnectError as _ce:
                _last_connect_err = _ce
                if _attempt < _max_retries - 1:
                    _wait = 0.5 * (2 ** _attempt)
                    logger.warning(
                        f"Ollama no responde (intento {_attempt+1}/{_max_retries}); "
                        f"reintento en {_wait:.1f}s…"
                    )
                    await asyncio.sleep(_wait)
        if _last_connect_err is not None:
            raise _last_connect_err

        data = response.json()

        # Extraer el contenido de la respuesta
        content = data.get("message", {}).get("content", "")
        if not content:
            content = data.get("response", "")  # Formato alternativo de Ollama

        latency_ms = (time.perf_counter() - t_start) * 1000

        logger.debug(
            f"Especialista '{specialist.id}' completado: "
            f"{latency_ms:.0f}ms, {len(content)} chars"
        )

        return {
            "specialist_id": specialist.id,
            "model_name": specialist.model_name,
            "content": content,
            "latency_ms": round(latency_ms, 1),
            "success": True,
            "error": None,
        }

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - t_start) * 1000
        error_msg = f"Timeout después de {timeout}s"
        logger.warning(f"Especialista '{specialist.id}': {error_msg}")
        return {
            "specialist_id": specialist.id,
            "model_name": specialist.model_name,
            "content": "",
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "error": error_msg,
        }

    except httpx.HTTPStatusError as exc:
        latency_ms = (time.perf_counter() - t_start) * 1000
        _model_missing = exc.response.status_code == 404
        if _model_missing:
            error_msg = (
                f"Modelo '{specialist.model_name}' no encontrado en Ollama. "
                f"Ejecuta: ollama pull {specialist.model_name}"
            )
        else:
            error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        logger.error(f"Especialista '{specialist.id}': {error_msg}")
        return {
            "specialist_id": specialist.id,
            "model_name": specialist.model_name,
            "content": "",
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "error": error_msg,
            "model_missing": _model_missing,
        }

    except httpx.ConnectError:
        latency_ms = (time.perf_counter() - t_start) * 1000
        error_msg = (
            "No se detecta Ollama en ejecución. Ábrelo (o ejecuta 'ollama serve') "
            "y reintenta — Andromeda volverá a conectar automáticamente."
        )
        logger.error(f"Especialista '{specialist.id}': Ollama offline en '{ollama_url}'")
        return {
            "specialist_id": specialist.id,
            "model_name": specialist.model_name,
            "content": "",
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "error": error_msg,
            "ollama_offline": True,
        }

    except Exception as exc:
        # Captura cualquier otro error inesperado
        latency_ms = (time.perf_counter() - t_start) * 1000
        error_msg = f"Error inesperado: {type(exc).__name__}: {str(exc)}"
        logger.error(f"Especialista '{specialist.id}': {error_msg}", exc_info=True)
        return {
            "specialist_id": specialist.id,
            "model_name": specialist.model_name,
            "content": "",
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "error": error_msg,
        }


# ── Señales de que el fallo es por CARGA (no por configuración) ─────────────
# Si el modelo no arranca porque el equipo no puede con él (memoria, timeout,
# error del runtime), tiene sentido reintentar con uno más ligero. Un 404
# (modelo no descargado) NO es de carga: ahí no reintentamos, avisamos.
_LOAD_ERROR_SIGNS = (
    "timeout", "out of memory", "oom", "memory", "cuda", "killed",
    "500", "503", "unavailable", "failed to load", "no space",
)


def _is_load_error(error: str | None) -> bool:
    if not error:
        return False
    e = error.lower()
    return any(sign in e for sign in _LOAD_ERROR_SIGNS)


async def call_with_fallback(
    specialist: SpecialistProfile,
    prompt: str,
    config: dict,
    *,
    level: str,
    models_by_level: dict[str, str],
) -> dict:
    """Ejecuta el especialista y, si falla por CARGA, reintenta bajando de nivel.

    En Lite el orquestador lineal elige un nivel de potencia. Si el modelo de ese
    nivel no arranca porque el hardware/software no lo soporta (out of memory,
    timeout, error del runtime), en vez de devolver un error al usuario probamos
    el modelo del nivel inmediatamente inferior, y así sucesivamente hasta 'low'.

    Args:
        level: nivel de potencia elegido por el orquestador (low/mid/high/ultra).
        models_by_level: mapa {nivel: model_name} con los modelos disponibles.

    Returns el primer resultado con éxito; si todos fallan, el último error, e
    incluye 'downgraded_to' si tuvo que bajar de nivel (para que la UI lo sepa).
    """
    from app.core.linear_orchestrator import fallback_chain

    available = {lv for lv, m in (models_by_level or {}).items() if m}
    chain = fallback_chain(level, available or None)

    last = None
    original_level = level
    for i, lv in enumerate(chain):
        model = (models_by_level or {}).get(lv)
        if not model:
            continue
        spec = specialist
        if spec.model_name != model:
            import copy
            spec = copy.copy(specialist)
            spec.model_name = model

        result = await _call_specialist(spec, prompt, config)

        if result.get("success"):
            if i > 0:  # tuvimos que bajar de nivel
                result["downgraded_from"] = original_level
                result["downgraded_to"] = lv
                logger.info(f"Fallback: '{original_level}' no arrancó, "
                            f"respondido con nivel '{lv}' ({model})")
            return result

        last = result
        # Si NO es error de carga (p.ej. modelo no descargado), no tiene sentido
        # seguir bajando: el problema no es la potencia. Devolvemos el error.
        if not _is_load_error(result.get("error")):
            return result
        logger.warning(f"Nivel '{lv}' falló por carga ({result.get('error')}); "
                       f"probando un nivel más ligero…")

    # Todos los niveles fallaron
    if last is not None:
        last["fallback_exhausted"] = True
    return last or {
        "specialist_id": specialist.id, "model_name": specialist.model_name,
        "content": "", "latency_ms": 0.0, "success": False,
        "error": "No se pudo ejecutar ningún nivel de potencia disponible.",
    }

