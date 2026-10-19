"""
skills.py — Andromeda Skills (Pro).

  GET  /api/skills            → lista de skills descubiertas
  GET  /api/skills/{id}        → detalle de una skill (incluye el cuerpo)
  POST /api/skills/reload      → re-escanea config/skills/ en caliente
  GET  /api/skills/match?q=    → qué skill(s) activaría un prompt dado (debug)
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def _registry(request: Request):
    return getattr(request.app.state, "skill_registry", None)


@router.get("")
async def list_skills(request: Request) -> JSONResponse:
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    return JSONResponse(content={"skills": reg.list_skills()})


@router.get("/match")
async def match_skills(request: Request, q: str = "") -> JSONResponse:
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    hits = reg.match(q, k=3)
    return JSONResponse(content={"query": q, "matched": [
        {"id": s.id, "name": s.name} for s in hits]})


@router.post("/reload")
async def reload_skills(request: Request) -> JSONResponse:
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    n = reg.reload()
    return JSONResponse(content={"reloaded": True, "count": n})


@router.get("/{skill_id}")
async def get_skill(request: Request, skill_id: str) -> JSONResponse:
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    sk = reg.get(skill_id)
    if sk is None:
        return JSONResponse(status_code=404, content={"error": "Skill no encontrada"})
    return JSONResponse(content={"id": sk.id, "name": sk.name, "description": sk.description,
                                 "specialists": sk.specialists, "body": sk.body})


@router.post("/user")
async def create_user_skill(request: Request) -> JSONResponse:
    """Crea o actualiza una skill propia del usuario."""
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    body = await request.json()
    try:
        sk = reg.save_user_skill(
            skill_id=body.get("id") or body.get("name", ""),
            name=body.get("name", ""),
            description=body.get("description", ""),
            body=body.get("body", ""),
            triggers=body.get("triggers", ""),
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(content={"saved": True, "id": sk.id, "name": sk.name})


@router.delete("/user/{skill_id}")
async def delete_user_skill(request: Request, skill_id: str) -> JSONResponse:
    """Borra una skill del usuario (las de fábrica no se pueden borrar)."""
    reg = _registry(request)
    if reg is None:
        return JSONResponse(status_code=503, content={"error": "Skills no disponibles"})
    sk = reg.get(skill_id)
    if sk and not sk.user_created:
        return JSONResponse(status_code=403,
                            content={"error": "Las skills de fábrica no se pueden borrar"})
    return JSONResponse(content={"deleted": reg.delete_user_skill(skill_id)})
