"""
compaction.py — Compactación de contexto de conversación.

Problema: los modelos locales tienen ventanas de contexto pequeñas (a menudo
4k-8k tokens frente a los 200k de un modelo en la nube). Cuando una
conversación crece, hay que decidir qué se queda fuera. La estrategia ingenua
—quedarse con los últimos N mensajes— descarta información antigua que puede
ser justo la importante: el nombre del proyecto, la decisión que se tomó al
principio, el fichero sobre el que se trabaja.

Este módulo aplica la estrategia que usan los asistentes de contexto largo:
cuando la conversación supera un umbral, los mensajes antiguos se resumen en
un bloque compacto y los recientes se conservan literalmente. Así el modelo
mantiene la memoria de lo hablado sin desbordar su ventana.

Dos modos de resumen:
  • Con Ollama disponible: se pide al modelo un resumen del tramo antiguo.
  • Sin Ollama (o si falla): resumen extractivo local, sin dependencias, que
    conserva las frases con más señal. Nunca se rompe ni se bloquea el chat.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("andromeda.compaction")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


# Aproximación de tokens: ~4 caracteres por token en español/inglés. Suficiente
# para decidir cuándo compactar; no hace falta un tokenizador real.
_CHARS_PER_TOKEN = 4
_KEEP_RECENT = 4            # mensajes recientes que se conservan literales
_SUMMARY_MAX_CHARS = 900    # techo del bloque de resumen

_SUMMARY_PROMPT = (
    "Resume esta conversación conservando: decisiones tomadas, datos concretos "
    "(nombres, rutas, cifras, versiones) y el objetivo del usuario. "
    "No añadas nada que no esté. Máximo 8 líneas, en el idioma de la conversación.\n\n"
)


def estimate_tokens(text: str) -> int:
    """Estimación barata del coste en tokens de un texto."""
    return len(text or "") // _CHARS_PER_TOKEN


def history_tokens(history: list[dict]) -> int:
    return sum(estimate_tokens(m.get("content", "")) for m in history or [])


def needs_compaction(history: list[dict], budget_tokens: int) -> bool:
    """True si el historial no cabe en el presupuesto de contexto asignado."""
    if not history or len(history) <= _KEEP_RECENT + 1:
        return False
    return history_tokens(history) > budget_tokens


def _extractive_summary(messages: list[dict]) -> str:
    """Resumen sin LLM: conserva las frases con más señal informativa.

    Heurística deliberadamente simple y predecible: puntúa cada frase por
    presencia de datos concretos (cifras, rutas, nombres propios, código) y
    penaliza las de puro relleno conversacional.
    """
    sentences: list[tuple[float, str]] = []
    for m in messages:
        who = "Usuario" if m.get("role") == "user" else "Asistente"
        content = (m.get("content") or "").strip()
        for raw in re.split(r"(?<=[.!?])\s+|\n+", content):
            s = raw.strip()
            if len(s) < 25 or len(s) > 300:
                continue
            score = 0.0
            score += 2.0 * len(re.findall(r"\d", s)) / max(len(s), 1) * 10   # cifras
            score += 1.5 if re.search(r"[/\\]\w+|\.\w{2,4}\b", s) else 0     # rutas/ficheros
            score += 1.5 if re.search(r"`[^`]+`", s) else 0                  # código
            score += 1.0 if re.search(r"\b[A-Z][a-z]{2,}\b", s) else 0       # nombres propios
            score += 1.0 if m.get("role") == "user" else 0                   # lo que pidió el usuario
            score -= 1.0 if re.match(r"^(vale|ok|gracias|perfecto|hola)\b", s.lower()) else 0
            if score > 0:
                sentences.append((score, f"{who}: {s}"))
    sentences.sort(key=lambda x: -x[0])
    out, total = [], 0
    for _, line in sentences:
        if total + len(line) > _SUMMARY_MAX_CHARS:
            break
        out.append(line)
        total += len(line)
    return "\n".join(out)


async def _llm_summary(messages: list[dict], ollama_url: str, model: str,
                       timeout: float = 20.0) -> str | None:
    """Pide el resumen al modelo local. Devuelve None si no está disponible."""
    if not ollama_url or not model:
        return None
    try:
        import httpx
        convo = "\n".join(
            f"{'Usuario' if m.get('role') == 'user' else 'Asistente'}: {m.get('content','')}"
            for m in messages)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{ollama_url.rstrip('/')}/api/chat", json={
                "model": model,
                "messages": [{"role": "user", "content": _SUMMARY_PROMPT + convo}],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            })
            r.raise_for_status()
            text = (r.json().get("message") or {}).get("content", "").strip()
            return text[:_SUMMARY_MAX_CHARS] or None
    except Exception as exc:
        logger.info(f"Resumen con LLM no disponible ({type(exc).__name__}); "
                    f"se usa resumen extractivo local")
        return None


async def compact_history(history: list[dict], budget_tokens: int,
                          ollama_url: str = "", model: str = "") -> tuple[list[dict], dict]:
    """Compacta el historial si hace falta.

    Devuelve (historial_compactado, info). `info` describe qué se hizo, para
    poder mostrarlo en la UI: el usuario debe saber cuándo se ha resumido su
    conversación, no es algo que deba ocurrir a sus espaldas.
    """
    if not needs_compaction(history, budget_tokens):
        return history, {"compacted": False}

    old, recent = history[:-_KEEP_RECENT], history[-_KEEP_RECENT:]
    before = history_tokens(history)

    summary = await _llm_summary(old, ollama_url, model)
    source = "llm"
    if not summary:
        summary = _extractive_summary(old)
        source = "extractive"
    if not summary:
        return history[-_KEEP_RECENT:], {"compacted": True, "source": "truncated",
                                         "messages_summarized": len(old)}

    compacted = [{"role": "system",
                  "content": f"[Resumen de {len(old)} mensajes anteriores]\n{summary}"}] + recent
    after = history_tokens(compacted)
    logger.info(f"Contexto compactado: {len(old)} mensajes → resumen "
                f"({before}→{after} tokens estimados, vía {source})")
    return compacted, {
        "compacted": True,
        "source": source,
        "messages_summarized": len(old),
        "tokens_before": before,
        "tokens_after": after,
    }
