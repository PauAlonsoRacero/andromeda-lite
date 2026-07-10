"""merger.py — STUB Lite. La fusión de respuestas es exclusiva de Pro.
En Lite hay una sola respuesta, no hay nada que fusionar."""
from __future__ import annotations
import logging
logger = logging.getLogger("andromeda.merger.lite")

async def merge_responses(responses, strategy="single", original_prompt="",
                          ollama_url=None, orchestrator_model=None, config=None):
    ok = [r for r in (responses or []) if r.get("success")]
    if not ok:
        return (responses[0].get("content", "") if responses else "") or ""
    return ok[0].get("content", "") or ""
