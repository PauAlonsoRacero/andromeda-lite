"""
confidence.py — Estimación ligera de la calidad/confianza de una respuesta.

Sin coste extra de LLM: analiza señales del propio texto para detectar respuestas
flojas (evasivas, demasiado cortas, repetitivas, truncadas). Andromeda Orquesta
la usa para decidir si vale la pena escalar a un tier de potencia superior.

No es perfecta — es una heurística barata. Su propósito es filtrar respuestas
claramente malas, no juzgar matices.
"""
from __future__ import annotations

import re

# Frases que delatan que el modelo no respondió de verdad.
_EVASIVE_MARKERS = [
    "no estoy seguro", "no puedo ayudar", "no puedo responder",
    "como ia no", "como modelo de lenguaje", "no tengo la capacidad",
    "lo siento, no", "no dispongo de", "no tengo información",
    "no soy capaz", "consulta a un experto", "te recomiendo buscar",
    "i cannot", "i'm not able", "as an ai",
]

# Señales de que se presenta en vez de responder (el bug de modelos pequeños).
_PRESENTATION_MARKERS = [
    "soy un asistente", "soy una ia", "estoy aquí para ayudarte",
    "¿en qué puedo ayudarte", "en qué puedo ayudarte", "¿cómo puedo ayudarte",
]


def estimate_confidence(prompt: str, response: str) -> float:
    """
    Devuelve una confianza en [0, 1]. Cuanto más alta, mejor pinta la respuesta.

    Penaliza: respuestas vacías o muy cortas para lo que se pidió, lenguaje
    evasivo, presentaciones en vez de respuestas, y repetición excesiva.
    """
    if not response or not response.strip():
        return 0.0

    text = response.strip()
    low = text.lower()
    score = 1.0

    # 1. Respuesta demasiado corta en relación a la pregunta
    words = len(text.split())
    if words < 5:
        score -= 0.4
    elif words < 15:
        score -= 0.15

    # 2. Lenguaje evasivo (no respondió de verdad)
    if any(m in low for m in _EVASIVE_MARKERS):
        score -= 0.45

    # 3. Se presenta en vez de responder
    if any(m in low for m in _PRESENTATION_MARKERS):
        # Solo penaliza si es una parte sustancial de la respuesta (corta)
        if words < 60:
            score -= 0.45

    # 4. Repetición excesiva (frases que se repiten)
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 5]
    if len(sentences) >= 2:
        unique = len(set(sentences))
        ratio = unique / len(sentences)
        if ratio < 0.6:           # más del 40% repetido
            score -= 0.25

    # 5. Truncamiento abrupto (acaba a media frase sin puntuación)
    if text and text[-1] not in ".!?)\"'`}]" and words > 20:
        score -= 0.1

    return max(0.0, min(1.0, round(score, 3)))


def should_escalate(confidence: float, current_tier: int, max_tier: int,
                    threshold: float = 0.5) -> bool:
    """
    Decide si reintentar en un tier de potencia superior.

    Solo escala si la confianza es baja Y queda margen de tier. Es deliberadamente
    conservador: escalar dobla la latencia, así que solo cuando merece la pena.
    """
    return confidence < threshold and current_tier < max_tier
