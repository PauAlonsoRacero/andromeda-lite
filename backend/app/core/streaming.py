"""
streaming.py — Staircase streaming de Andromeda.

Implementa el streaming real token a token desde Ollama hacia el cliente SSE.

Fase 0 (este archivo): streaming completo — lanza todos los especialistas
en paralelo, el primero que genera tokens los envía al cliente inmediatamente.
El cliente ve tokens aparecer en <800ms en T2 en lugar de esperar 10-25s.

Arquitectura del staircase:
  1. Lanzar N streams de Ollama simultáneamente (asyncio.gather)
  2. El primer especialista que genera un token → enviarlo al cliente (TTFT)
  3. Continuar recibiendo tokens de todos en paralelo
  4. Cuando todos terminan → invocar merger con los outputs completos
  5. Enviar chunk final con metadata (trace_id, latencias, estrategia)

Protocolo SSE al cliente:
  data: {"chunk_id":"...","request_id":"...","content":"token","specialist_id":"sw-eng","is_final":false}
  data: {"chunk_id":"...","request_id":"...","content":"","is_final":true,"metadata":{...}}
  data: [DONE]

Uso desde chat.py:
    async for chunk in staircase_stream(specialists, prompt, config, request_id):
        yield f"data: {json.dumps(chunk)}\n\n"
    yield "data: [DONE]\n\n"
"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

import httpx

from app.models.schemas import SpecialistProfile
from app.specialists.identity import with_identity

logger = logging.getLogger("andromeda.streaming")


async def staircase_stream(
    specialists: list[SpecialistProfile],
    prompt: str,
    config: dict,
    request_id: str,
    use_output_ai: bool = False,
    output_model: str | None = None,
    escalation: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Genera chunks SSE en streaming real token a token.

    Lanza N llamadas a Ollama simultáneamente usando asyncio.
    Los tokens del primer especialista en responder se envían inmediatamente.
    El TTFT típico en T2 es <800ms vs 10-25s en modo no-streaming.

    Args:
        specialists:  Lista de especialistas a ejecutar
        prompt:       Prompt del usuario
        config:       {ollama_url, temperature, max_tokens, timeout, strategy}
        request_id:   UUID del request (para correlación)

    Yields:
        Dicts con la estructura de ChatChunk — listos para serializar como SSE.
        El último chunk tiene is_final=True y lleva los metadatos completos.
    """
    ollama_url  = config.get("ollama_url",  "http://localhost:11434")
    temperature = config.get("temperature", 0.7)
    max_tokens  = config.get("max_tokens",  2048)
    timeout_s   = config.get("timeout",     120)
    strategy    = config.get("strategy",    "single")

    # Verificar que la URL de Ollama funciona; si no, re-resolver entre candidatas.
    # Esto garantiza que el chat use la URL correcta aunque settings esté desfasado.
    from app.ollama_resolver import resolve_ollama_url
    resolved = await resolve_ollama_url(ollama_url)
    if resolved:
        ollama_url = resolved

    t_start = time.perf_counter()
    ttft_ms = None

    # Almacena el output completo de cada especialista para el merger posterior
    outputs: dict[str, str]   = {}
    latencies: dict[str, float] = {}
    errors: dict[str, str]    = {}

    # Cola compartida donde todos los streams depositan sus tokens
    # (specialist_id, token_text) o (specialist_id, None) cuando termina
    queue: asyncio.Queue = asyncio.Queue()

    async def stream_specialist(specialist: SpecialistProfile) -> None:
        """
        Llama a la API de streaming de Ollama y pone cada token en la cola.
        Nunca lanza excepción al exterior.
        """
        t0 = time.perf_counter()
        accumulated = ""

        payload = {
            "model": specialist.model_name,
            "messages": [
                {"role": "system", "content": with_identity(specialist.system_prompt, specialist.id, specialist.model_name)},
                {"role": "user",   "content": prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": True,   # ← modo streaming de Ollama: NDJSON
        }

        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{ollama_url}/api/chat",
                    json=payload,
                    timeout=timeout_s,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Ollama envía: {"message":{"content":"token"},"done":false}
                        token = data.get("message", {}).get("content", "")
                        done  = data.get("done", False)

                        if token:
                            accumulated += token
                            # No emitir en vivo el monólogo interno de modelos de
                            # razonamiento: si estamos dentro de <think>…</think>,
                            # acumulamos pero no enviamos al usuario.
                            if "<think>" in accumulated and "</think>" not in accumulated:
                                pass  # dentro del bloque de razonamiento: silenciar
                            elif token.strip() in ("<think>", "</think>"):
                                pass  # no mostrar las etiquetas
                            else:
                                await queue.put((specialist.id, token, False))

                        if done:
                            break

            # Especialista terminó correctamente.
            # Modelos de razonamiento (deepseek-r1, qwq...) emiten <think>...</think>
            # con su monólogo interno. Lo retiramos del resultado guardado para
            # que el merger y el historial queden limpios.
            import re as _re
            clean = _re.sub(r"<think>.*?</think>", "", accumulated, flags=_re.DOTALL).strip()
            if not clean:
                clean = accumulated.strip()
            latency = (time.perf_counter() - t0) * 1000
            outputs[specialist.id]   = clean
            latencies[specialist.id] = round(latency, 1)
            logger.debug(
                f"[{request_id[:8]}] Stream {specialist.id}: "
                f"{len(accumulated)} chars, {latency:.0f}ms"
            )

        except httpx.TimeoutException:
            errors[specialist.id] = f"Timeout después de {timeout_s}s"
            logger.warning(f"[{request_id[:8]}] Timeout en stream {specialist.id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                errors[specialist.id] = (
                    f"Modelo '{specialist.model_name}' no encontrado. "
                    f"Ejecuta: ollama pull {specialist.model_name}"
                )
            else:
                errors[specialist.id] = f"HTTP {exc.response.status_code}"
            logger.error(f"[{request_id[:8]}] HTTPError en {specialist.id}: {errors[specialist.id]}")
        except Exception as exc:
            errors[specialist.id] = str(exc)
            logger.error(f"[{request_id[:8]}] Error en stream {specialist.id}: {exc}")
        finally:
            # Señal de fin para este especialista
            await queue.put((specialist.id, None, True))

    # Lanzar todos los streams en paralelo
    tasks = [asyncio.create_task(stream_specialist(s)) for s in specialists]

    finished = 0
    total    = len(specialists)

    # Mostramos tokens en vivo SOLO con 1 IA y SIN escalado por reintento.
    # Con varias IAs los tokens llegan intercalados (ilegible). Con escalado
    # activo, acumulamos en silencio para evaluar la confianza y poder reintentar
    # en un tier superior antes de mostrar nada.
    escalation_on = bool(escalation and escalation.get("enabled"))
    stream_live = (total == 1) and not escalation_on
    announced: set[str] = set()

    while finished < total:
        try:
            spec_id, token, is_done = await asyncio.wait_for(
                queue.get(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{request_id[:8]}] Timeout global esperando tokens")
            break

        if is_done:
            finished += 1
            # En multi-IA, informar del progreso (X de N IAs listas)
            if not stream_live:
                yield {
                    "chunk_id":      str(uuid.uuid4()),
                    "request_id":    request_id,
                    "content":       "",
                    "specialist_id": spec_id,
                    "is_final":      False,
                    "metadata":      {"stage": "progress", "done": finished, "total": total},
                }
            continue

        if ttft_ms is None:
            ttft_ms = round((time.perf_counter() - t_start) * 1000, 1)
            logger.info(f"[{request_id[:8]}] TTFT: {ttft_ms}ms (spec={spec_id})")

        if stream_live:
            # 1 IA: streaming fluido token a token.
            yield {
                "chunk_id":      str(uuid.uuid4()),
                "request_id":    request_id,
                "content":       token,
                "specialist_id": spec_id,
                "is_final":      False,
                "metadata":      {},
            }
        else:
            # Multi-IA: no emitir el token crudo. Anunciar una vez qué IA arrancó
            # (para el indicador de progreso del frontend) y acumular en silencio.
            if spec_id not in announced:
                announced.add(spec_id)
                yield {
                    "chunk_id":      str(uuid.uuid4()),
                    "request_id":    request_id,
                    "content":       "",
                    "specialist_id": spec_id,
                    "is_final":      False,
                    "metadata":      {"stage": "working", "specialist": spec_id},
                }


    # Esperar que todas las tareas terminen limpiamente
    await asyncio.gather(*tasks, return_exceptions=True)

    # Calcular latencia total
    total_latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

    # Si todos fallaron → enviar error
    if not outputs and errors:
        error_msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
        yield {
            "chunk_id":   str(uuid.uuid4()),
            "request_id": request_id,
            "content":    f"\n\n⚠️ Error: {error_msg}",
            "is_final":   True,
            "metadata": {
                "error":        True,
                "error_detail": error_msg,
                "latency_ms":   total_latency_ms,
                "ttft_ms":      ttft_ms or 0,
            },
        }
        return

    # ── ESCALADO POR REINTENTO (Andromeda Orquesta) ──────────────────────────
    # Con 1 IA y escalado activo: si la respuesta tiene baja confianza y queda
    # margen de tier, reintentamos UNA vez con el modelo del tier superior.
    # Es la materialización de "subir escalafones de potencia a conveniencia":
    # se gasta lo mínimo por defecto y solo se escala cuando hace falta.
    escalated_info = None
    if escalation_on and total == 1 and outputs:
        from app.core.confidence import estimate_confidence, should_escalate
        sid0 = next(iter(outputs))
        first_text = outputs[sid0]
        conf = estimate_confidence(prompt, first_text)
        cur_tier = escalation.get("power_tier", 1)
        max_tier = escalation.get("max_tier", 4)
        if should_escalate(conf, cur_tier, max_tier):
            registry = escalation.get("registry")
            hw_tier = escalation.get("hardware_tier", max_tier)
            vram = escalation.get("vram_free_gb", 999.0)
            target_tier = cur_tier + 1
            try:
                # Resolver el modelo del tier superior para ese especialista.
                bigger_model, level = registry.resolve_model_for_tier(
                    sid0, hw_tier, vram, power_tier=target_tier)
                if bigger_model and bigger_model != specialists[0].model_name:
                    logger.info(f"[{request_id[:8]}] Escalado: conf={conf:.2f} "
                                f"→ reintento tier {target_tier} ({bigger_model})")
                    # Reintento con el modelo mayor (no streaming, recogemos todo).
                    retry_out = await _run_single(
                        specialists[0], bigger_model, prompt, config,
                        ollama_url, timeout_s, max_tokens)
                    if retry_out and retry_out.strip():
                        new_conf = estimate_confidence(prompt, retry_out)
                        # Nos quedamos con la mejor de las dos respuestas.
                        if new_conf >= conf:
                            outputs[sid0] = retry_out
                            escalated_info = {
                                "escalated": True,
                                "from_tier": cur_tier, "to_tier": target_tier,
                                "from_conf": conf, "to_conf": new_conf,
                                "model": bigger_model,
                            }
            except Exception as _ee:
                logger.warning(f"[{request_id[:8]}] Escalado falló: {_ee}")

    # Aplicar merger con los outputs completos
    # Import aquí para evitar circular imports
    from app.core.merger import merge_responses

    merged_content = await merge_responses(
        responses=[
            {
                "specialist_id": sid,
                "content":       content,
                "latency_ms":    latencies.get(sid, 0),
                "success":       True,
                "model_name":    next(
                    (s.model_name for s in specialists if s.id == sid),
                    "unknown"
                ),
            }
            for sid, content in outputs.items()
        ],
        strategy=strategy,
        original_prompt=prompt,
        ollama_url=ollama_url,
        orchestrator_model=config.get("orchestrator_model", ""),
        config=config,
        skip_interpret=bool(use_output_ai and output_model),
    )

    # ── ETAPA 4: RESPUESTA FINAL (fusión + IA de salida) ──────────────────────
    # En multi-IA no se streameó nada crudo, así que aquí emitimos la respuesta
    # final LIMPIA. Con IA de salida: streaming del texto pulido. Sin ella: el
    # resultado de la fusión de una vez.
    # (outputs puede haber sido actualizado por el escalado por reintento)
    streamed_content = "".join(outputs.values())
    multi = (total >= 2)

    if use_output_ai and output_model and merged_content and merged_content.strip():
        from app.core.output_ai import stream_polished_output
        # En multi-IA la respuesta unificada ES la respuesta (sin separador).
        # En 1-IA (no debería ocurrir aquí) mantenemos un separador suave.
        if not multi:
            yield {
                "chunk_id": str(uuid.uuid4()), "request_id": request_id,
                "content": "\n\n---\n", "specialist_id": "output",
                "is_final": False, "metadata": {"stage": "output_ai"},
            }
        async for tok, done in stream_polished_output(
            user_prompt=prompt,
            fused_content=merged_content,
            output_model=output_model,
            ollama_url=ollama_url,
            timeout=timeout_s,
            max_tokens=max_tokens,
        ):
            if tok:
                yield {
                    "chunk_id":      str(uuid.uuid4()),
                    "request_id":    request_id,
                    "content":       tok,
                    "specialist_id": "output",
                    "is_final":      False,
                    "metadata":      {"stage": "output_ai"},
                }
    elif multi and merged_content and merged_content.strip():
        # Multi-IA sin IA de salida (falló o sin modelo): emitir la fusión limpia.
        yield {
            "chunk_id":      str(uuid.uuid4()),
            "request_id":    request_id,
            "content":       merged_content,
            "specialist_id": "merger",
            "is_final":      False,
            "metadata":      {"stage": "fusion"},
        }
    elif merged_content and merged_content != streamed_content:
        # 1-IA donde el merger refinó (p.ej. iterative_refine): enviar refinado.
        yield {
            "chunk_id":      str(uuid.uuid4()),
            "request_id":    request_id,
            "content":       "\n\n---\n**Respuesta refinada:**\n" + merged_content,
            "specialist_id": "merger",
            "is_final":      False,
            "metadata":      {},

        }
    elif not stream_live and total == 1 and streamed_content.strip():
        # 1 IA con escalado activo: no se streameó en vivo (se acumuló para poder
        # reintentar). Emitir ahora la respuesta final (posiblemente la escalada).
        yield {
            "chunk_id":      str(uuid.uuid4()),
            "request_id":    request_id,
            "content":       streamed_content,
            "specialist_id": next(iter(outputs)),
            "is_final":      False,
            "metadata":      {"stage": "escalated"} if escalated_info else {},
        }

    # Chunk final con todos los metadatos
    # (El tracking MLOps se hace en el route de chat, que tiene acceso al app.state)
    yield {
        "chunk_id":   str(uuid.uuid4()),
        "request_id": request_id,
        "content":    "",
        "is_final":   True,
        "metadata": {
            "specialists_used":    list(outputs.keys()),
            "models_used":         {
                sid: next((s.model_name for s in specialists if s.id == sid),
                          "unknown")
                for sid in outputs.keys()
            },
            "strategy_used":       strategy,
            "latency_ms":          total_latency_ms,
            "ttft_ms":             ttft_ms or 0,
            "latencies_by_spec":   latencies,
            "errors":              errors if errors else None,
            "degraded":            False,
            "degradation_reason":  None,
            "output_ai_used":      bool(use_output_ai and output_model),
            "escalated":           escalated_info,
        },
    }


async def _run_single(specialist, model_name, prompt, config,
                      ollama_url, timeout_s, max_tokens):
    """
    Ejecuta UN modelo concreto en modo no-streaming y devuelve el texto completo.
    Lo usa el escalado por reintento para regenerar con un modelo de tier superior.
    Filtra el monólogo <think>…</think> de los modelos de razonamiento.
    """
    import re as _re
    temperature = config.get("temperature", 0.7)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": with_identity(specialist.system_prompt, specialist.id, specialist.model_name)},
            {"role": "user",   "content": prompt},
        ],
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(f"{ollama_url}/api/chat", json=payload, timeout=timeout_s)
            r.raise_for_status()
            data = r.json()
            text = data.get("message", {}).get("content", "") or ""
            # Quitar el bloque <think>…</think> de modelos de razonamiento
            text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
            return text
    except Exception:
        return ""
