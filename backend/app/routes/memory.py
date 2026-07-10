"""
memory.py — API de memoria semántica de Andromeda.

GET  /api/memory/stats         → estadísticas del memory store
GET  /api/memory/search?q=...  → buscar memorias relevantes
POST /api/memory               → guardar una memoria manualmente
DELETE /api/memory/{id}        → eliminar una memoria
DELETE /api/memory             → limpiar toda la memoria
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.memory")
router = APIRouter()


def _get_memory(request: Request):
    return getattr(request.app.state, 'memory_store', None)


def _get_profile(request: Request):
    return getattr(request.app.state, 'memory_profile', None)


# ── Perfil de memoria unificado (estilo Claude: un solo bloque) ──────────────

@router.get("/profile")
async def get_profile(request: Request) -> JSONResponse:
    prof = _get_profile(request)
    if not prof:
        return JSONResponse(content={"text": "", "facts": {}, "manual": "", "is_empty": True})
    return JSONResponse(content=prof.get())


@router.put("/profile")
async def set_profile(request: Request) -> JSONResponse:
    """El usuario edita el bloque entero a mano. Body: {"text": "..."}"""
    prof = _get_profile(request)
    if not prof:
        return JSONResponse(status_code=503, content={"error": "Perfil no disponible"})
    body = await request.json()
    prof.set_manual(body.get("text", ""))
    return JSONResponse(content=prof.get())


@router.delete("/profile/fact/{topic}")
async def delete_profile_fact(topic: str, request: Request) -> JSONResponse:
    prof = _get_profile(request)
    if not prof:
        return JSONResponse(status_code=503, content={"error": "Perfil no disponible"})
    ok = prof.delete_fact(topic)
    return JSONResponse(content={"success": ok, **prof.get()})


@router.delete("/profile")
async def clear_profile(request: Request) -> JSONResponse:
    prof = _get_profile(request)
    if prof:
        prof.clear()
    return JSONResponse(content={"success": True})


@router.get("/stats")
async def memory_stats(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(content={"enabled": False, "total": 0})
    stats = mem.get_stats()
    stats["enabled"] = True
    return JSONResponse(content=stats)


@router.get("/search")
async def search_memory(q: str, k: int = 5, request: Request = None) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(content={"results": [], "enabled": False})
    results = await mem.search(q, k=k)
    return JSONResponse(content={"results": results, "count": len(results)})


@router.get("/list")
async def list_memories(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error": "Memoria no disponible"})
    items = await mem.list_all()
    return JSONResponse(content={"memories": items, "count": len(items)})


@router.post("")
async def save_memory(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error": "Memoria no disponible"})
    body     = await request.json()
    content  = body.get("content", "")
    source   = body.get("source", "manual")
    category = body.get("category", "general")
    if not content.strip():
        return JSONResponse(status_code=400, content={"error": "content requerido"})
    mem_id = await mem.save(content=content, source=source, category=category, importance=0.8)
    return JSONResponse(content={"success": True, "id": mem_id})


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error": "Memoria no disponible"})
    await mem.delete(memory_id)
    return JSONResponse(content={"success": True})


@router.delete("")
async def clear_memory(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error": "Memoria no disponible"})
    count = await mem.clear()
    return JSONResponse(content={"success": True, "deleted": count})
