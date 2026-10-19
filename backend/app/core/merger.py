"""merger.py — STUB Lite. La fusión de respuestas es exclusiva de Pro.
En Lite hay una sola respuesta, no hay nada que fusionar.
NOTA: stub en Lite. La fusión de respuestas requiere varias IAs en paralelo,
que es funcionalidad de Pro. La firma se mantiene para que el pipeline sea
idéntico en las dos ediciones.
"""
from __future__ import annotations
import logging
logger = logging.getLogger("andromeda.merger.lite")

async def merge_responses(responses, strategy="single", original_prompt="",
                          ollama_url=None, orchestrator_model=None, config=None,
                          **_pro_kwargs):
    # **_pro_kwargs: el streaming comparte código con Pro y le pasa parámetros
    # que solo existen allí (p. ej. skip_interpret). Sin aceptarlos, esta
    # función lanzaba TypeError al final de CADA respuesta en streaming: el
    # texto se veía, pero la respuesta terminaba en error, sin metadatos ni id.
    ok = [r for r in (responses or []) if r.get("success")]
    if not ok:
        return (responses[0].get("content", "") if responses else "") or ""
    return ok[0].get("content", "") or ""
