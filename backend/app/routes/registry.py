"""
registry.py (rutas) — API del Model Registry.

GET    /api/registry              → lista de versiones registradas
POST   /api/registry              → registrar una versión {model, version?, eval_score?, notes?}
POST   /api/registry/{id}/promote → cambiar estado {stage: staging|production|archived}
GET    /api/registry/production   → modelo actualmente en producción
DELETE /api/registry/{id}         → eliminar una versión
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.registry")
router = APIRouter()


def _reg(request: Request):
    return getattr(request.app.state, "model_registry", None)


@router.get("")
async def list_versions(request: Request) -> JSONResponse:
    reg = _reg(request)
    if not reg:
        return JSONResponse(content={"versions": []})
    return JSONResponse(content={"versions": reg.list()})


@router.post("")
async def register_version(request: Request) -> JSONResponse:
    reg = _reg(request)
    if not reg:
        return JSONResponse(status_code=503, content={"error": "Registry no disponible"})
    body = await request.json()
    model = (body.get("model") or "").strip()
    if not model:
        return JSONResponse(status_code=400, content={"error": "Falta 'model'"})
    entry = reg.register(
        model=model,
        version=body.get("version", ""),
        eval_score=body.get("eval_score"),
        notes=body.get("notes", ""),
    )
    return JSONResponse(content=entry)


@router.post("/{vid}/promote")
async def promote_version(vid: str, request: Request) -> JSONResponse:
    reg = _reg(request)
    if not reg:
        return JSONResponse(status_code=503, content={"error": "Registry no disponible"})
    body = await request.json()
    stage = (body.get("stage") or "").strip()
    try:
        entry = reg.promote(vid, stage)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "Versión no encontrada"})
    return JSONResponse(content=entry)


@router.get("/production")
async def get_production(request: Request) -> JSONResponse:
    reg = _reg(request)
    entry = reg.production_entry() if reg else None
    return JSONResponse(content={"production": entry})


@router.delete("/{vid}")
async def delete_version(vid: str, request: Request) -> JSONResponse:
    reg = _reg(request)
    if not reg:
        return JSONResponse(status_code=503, content={"error": "Registry no disponible"})
    ok = reg.delete(vid)
    return JSONResponse(content={"success": ok})
