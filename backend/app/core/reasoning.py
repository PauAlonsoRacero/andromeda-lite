"""
reasoning.py — Mismo modelo, más o menos cómputo.

Los modelos de razonamiento pueden pensar antes de responder o no. Ollama lo
controla con el parámetro `think` (booleano; en gpt-oss, "low" | "medium" | "high").
Es la forma real de graduar la potencia SIN cambiar de modelo:

    Rápido / Equilibrado  → sin razonamiento (responde al momento)
    Fuerte                → razona (gpt-oss: esfuerzo medio)
    Máximo                → razona a fondo (gpt-oss: esfuerzo alto)

Además, qwen3 razona SIEMPRE por defecto: hasta un "hola" generaba un
razonamiento oculto largo antes de contestar. Con esto, los mensajes sencillos
van directos.

Solo se envía a familias que lo admiten: a un modelo sin razonamiento, Ollama
responde con error.
"""
from __future__ import annotations

_BOOLEANO = ("qwen3", "deepseek-r1", "qwq", "magistral", "phi4-reasoning", "cogito")
_ESFUERZO = ("gpt-oss",)
_SIN_RAZONAMIENTO = ("qwen3-coder", "qwen3-vl", "qwen3-embedding")


def supports_thinking(model: str | None) -> bool:
    m = (model or "").lower()
    if any(m.startswith(x) for x in _SIN_RAZONAMIENTO):
        return False
    return any(m.startswith(x) for x in _BOOLEANO + _ESFUERZO)


def think_option(model: str | None, level: str | None):
    """Valor de `think` para Ollama, o None si no hay que enviarlo."""
    if not supports_thinking(model):
        return None
    m = (model or "").lower()
    nivel = (level or "").lower()
    if any(m.startswith(x) for x in _ESFUERZO):
        return {"low": "low", "mid": "low", "high": "medium", "ultra": "high"}.get(nivel, "medium")
    if nivel in ("low", "mid"):
        return False
    if nivel in ("high", "ultra"):
        return True
    return None          # sin nivel conocido: el comportamiento por defecto del modelo


def apply(payload: dict, model: str | None, level: str | None) -> dict:
    valor = think_option(model, level)
    if valor is not None:
        payload["think"] = valor
    return payload
