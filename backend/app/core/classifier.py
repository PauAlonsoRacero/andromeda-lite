"""classifier.py — STUB Lite. La orquestación multi-IA es exclusiva de Pro.
En Lite no hay clasificación de especialistas: siempre el generalista."""
from __future__ import annotations
import logging
logger = logging.getLogger("andromeda.classifier.lite")

async def classify_prompt(prompt, available_specialists, hardware_policy=None,
                          ollama_url=None, orchestrator_model=None, orchestrator_active=False):
    chosen = None
    for s in available_specialists or []:
        if getattr(s, "id", None) == "generalist":
            chosen = s; break
    if chosen is None and available_specialists:
        chosen = available_specialists[0]
    sid = getattr(chosen, "id", "generalist") if chosen else "generalist"
    return {"specialists": [sid], "strategy": "single", "confidence": 1.0,
            "reasoning": "Lite: IA única", "source": "lite-linear"}
