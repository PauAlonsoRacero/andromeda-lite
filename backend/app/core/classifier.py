"""classifier.py — STUB Lite. La orquestación multi-IA es exclusiva de Pro.
En Lite no hay clasificación de especialistas: siempre el generalista.
NOTA: stub en Lite. El clasificador multi-IA (elegir qué especialistas atienden
cada prompt) pertenece a Pro; aquí se conserva la firma para que el router
funcione igual en ambas ediciones.
"""
from __future__ import annotations
import logging
logger = logging.getLogger("andromeda.classifier.lite")

async def classify_prompt(prompt, available_specialists, hardware_policy=None,
                          ollama_url=None, orchestrator_model=None, orchestrator_active=False,
                          **_pro_kwargs):
    # **_pro_kwargs: mismo motivo que en merger.py. El código compartido con
    # Pro puede pasar parámetros que este esqueleto de Lite no usa; sin
    # aceptarlos, una llamada nueva desde Pro rompería Lite en tiempo de ejecución.
    chosen = None
    for s in available_specialists or []:
        if getattr(s, "id", None) == "generalist":
            chosen = s; break
    if chosen is None and available_specialists:
        chosen = available_specialists[0]
    sid = getattr(chosen, "id", "generalist") if chosen else "generalist"
    return {"specialists": [sid], "strategy": "single", "confidence": 1.0,
            "reasoning": "Lite: IA única", "source": "lite-linear"}
