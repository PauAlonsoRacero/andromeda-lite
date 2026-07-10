"""
output_ai.py — Etapa 4 del pipeline: la IA de salida.

Toma el resultado de la fusión (etapa 3) y hace una pasada final que:
  - unifica el tono y el estilo (varias IAs suenan distinto),
  - elimina redundancias y contradicciones entre las respuestas,
  - asegura que responde exactamente a lo que el usuario preguntó,
  - entrega un texto final limpio y coherente.

Solo se ejecuta cuando hubo 2+ IAs (decisión del orquestador). Si la IA de
salida falla o no responde, se devuelve el texto fusionado tal cual (nunca
deja al usuario sin respuesta).
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("andromeda.output_ai")

_OUTPUT_SYSTEM = (
    "Eres el editor final de un sistema multi-IA. Recibes borradores de varios "
    "modelos especializados sobre la misma pregunta. Produce UNA respuesta final "
    "excelente: toma lo mejor de cada borrador, corrige errores, elimina "
    "repeticiones y relleno, y organiza todo con claridad. "
    "Responde directamente a la pregunta del usuario — sin presentarte, sin decir "
    "'soy un asistente', sin meta-comentarios sobre los modelos o el proceso. "
    "Si la pregunta pide código o un documento, entrégalo completo y bien formateado "
    "en Markdown. Usa el idioma del usuario. Empieza directamente con la respuesta."
)


async def polish_output(
    *,
    user_prompt: str,
    fused_content: str,
    output_model: str,
    ollama_url: str,
    timeout: float = 90.0,
    max_tokens: int = 3000,
) -> str:
    """
    Pasada final de pulido. Devuelve el texto refinado, o `fused_content`
    intacto si algo falla (garantía de no-vacío).
    """
    if not fused_content or not fused_content.strip():
        return fused_content
    if not output_model:
        return fused_content

    user_msg = (
        f"PREGUNTA DEL USUARIO:\n{user_prompt}\n\n"
        f"RESPUESTA COMBINADA DE LOS ESPECIALISTAS:\n{fused_content}\n\n"
        f"Entrega la versión final, pulida y coherente:"
    )
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": output_model,
                    "messages": [
                        {"role": "system", "content": _OUTPUT_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "options": {"temperature": 0.3, "num_predict": max_tokens},
                    "stream": False,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
        content = (resp.json().get("message", {}) or {}).get("content", "") or ""
        # Limpiar posible razonamiento <think> de modelos de razonamiento
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content or fused_content
    except Exception as exc:
        logger.warning(f"IA de salida falló ({exc}); devolviendo fusión sin pulir")
        return fused_content


async def stream_polished_output(
    *,
    user_prompt: str,
    fused_content: str,
    output_model: str,
    ollama_url: str,
    timeout: float = 90.0,
    max_tokens: int = 3000,
):
    """
    Variante en streaming: emite el texto pulido token a token.
    Yields (token, done). Si falla, emite el fused_content de una vez.
    """
    if not fused_content or not fused_content.strip() or not output_model:
        yield (fused_content, True)
        return

    user_msg = (
        f"PREGUNTA DEL USUARIO:\n{user_prompt}\n\n"
        f"RESPUESTA COMBINADA DE LOS ESPECIALISTAS:\n{fused_content}\n\n"
        f"Entrega la versión final, pulida y coherente:"
    )
    import json as _json
    in_think = False
    emitted_any = False
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{ollama_url}/api/chat",
                json={
                    "model": output_model,
                    "messages": [
                        {"role": "system", "content": _OUTPUT_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    "options": {"temperature": 0.3, "num_predict": max_tokens},
                    "stream": True,
                },
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    tok = (data.get("message", {}) or {}).get("content", "")
                    done = data.get("done", False)
                    if tok:
                        # filtrar bloques de razonamiento
                        if "<think>" in tok:
                            in_think = True
                        if in_think:
                            if "</think>" in tok:
                                in_think = False
                            continue
                        if tok.strip() in ("<think>", "</think>"):
                            continue
                        emitted_any = True
                        yield (tok, False)
                    if done:
                        break
        if not emitted_any:
            # El modelo no produjo nada útil → entregar la fusión
            yield (fused_content, True)
        else:
            yield ("", True)
    except Exception as exc:
        logger.warning(f"IA de salida (stream) falló ({exc}); entregando fusión")
        if not emitted_any:
            yield (fused_content, True)
        else:
            yield ("", True)
