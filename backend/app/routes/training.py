"""routes/training.py — Corpus de entrenamiento para Apolo."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.training")
router = APIRouter(prefix="/api/training", tags=["Training"])


def _corpus(request: Request):
    return getattr(request.app.state, "training_corpus", None)


@router.get("")
async def get_stats(request: Request) -> JSONResponse:
    c = _corpus(request)
    if c is None:
        return JSONResponse(status_code=503, content={"error_key": "err.training_unavailable"})
    return JSONResponse(c.stats())


@router.put("")
async def set_enabled(request: Request) -> JSONResponse:
    c = _corpus(request)
    if c is None:
        return JSONResponse(status_code=503, content={"error_key": "err.training_unavailable"})
    body = await request.json()
    c.set_enabled(bool(body.get("enabled", False)))
    return JSONResponse(c.stats())


@router.post("/export")
async def export(request: Request) -> JSONResponse:
    """Exporta train.jsonl y valid.jsonl a Descargas, listos para mlx_lm.lora."""
    c = _corpus(request)
    if c is None:
        return JSONResponse(status_code=503, content={"error_key": "err.training_unavailable"})
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    destino = Path.home() / "Downloads" / "andromeda-apolo-dataset"
    resultado = c.export_mlx(destino, include_unrated=bool(body.get("include_unrated", False)))
    # El comando exacto para entrenar, para no tener que buscarlo.
    resultado["command"] = (
        f"mlx_lm.lora --model <modelo> --train --data \"{destino}\" --iters 1000"
    )
    return JSONResponse(resultado)


@router.delete("")
async def clear(request: Request) -> JSONResponse:
    c = _corpus(request)
    if c is None:
        return JSONResponse(status_code=503, content={"error_key": "err.training_unavailable"})
    c.clear()
    return JSONResponse(c.stats())
