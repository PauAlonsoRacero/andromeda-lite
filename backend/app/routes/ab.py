"""
ab.py — API del framework de A/B testing de modelos.

GET    /api/ab                 → lista experimentos
POST   /api/ab                 → crea un experimento
GET    /api/ab/{id}/results    → resultados (tasa de éxito, latencia, ganador)
POST   /api/ab/{id}/active     → activar/desactivar
DELETE /api/ab/{id}            → eliminar
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.ab")
router = APIRouter()


def _ab(request: Request):
    return getattr(request.app.state, "ab_testing", None)


@router.get("")
async def list_experiments(request: Request) -> JSONResponse:
    ab = _ab(request)
    if not ab:
        return JSONResponse(content={"experiments": []})
    return JSONResponse(content={"experiments": ab.list()})


@router.post("")
async def create_experiment(request: Request) -> JSONResponse:
    ab = _ab(request)
    if not ab:
        return JSONResponse(status_code=503, content={"error": "A/B no disponible"})
    body = await request.json()
    exp_id = (body.get("id") or "").strip()
    variants = body.get("variants") or []
    if not exp_id or len(variants) < 2:
        return JSONResponse(status_code=400,
                            content={"error": "Se requiere 'id' y al menos 2 variantes"})
    exp = ab.create(exp_id, variants, active=bool(body.get("active", True)))
    return JSONResponse(content=exp)


@router.get("/{exp_id}/results")
async def experiment_results(exp_id: str, request: Request) -> JSONResponse:
    ab = _ab(request)
    res = ab.results(exp_id) if ab else None
    if res is None:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    return JSONResponse(content=res)


@router.post("/{exp_id}/active")
async def set_active(exp_id: str, request: Request) -> JSONResponse:
    ab = _ab(request)
    body = await request.json()
    ok = ab.set_active(exp_id, bool(body.get("active", True))) if ab else False
    return JSONResponse(content={"success": ok})


@router.delete("/{exp_id}")
async def delete_experiment(exp_id: str, request: Request) -> JSONResponse:
    ab = _ab(request)
    ok = ab.delete(exp_id) if ab else False
    return JSONResponse(content={"success": ok})
