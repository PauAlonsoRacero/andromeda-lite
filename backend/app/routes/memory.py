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
        return JSONResponse(status_code=503, content={"error_key": "err.profile_unavailable"})
    body = await request.json()
    prof.set_manual(body.get("text", ""))
    return JSONResponse(content=prof.get())


@router.delete("/profile/fact/{topic}")
async def delete_profile_fact(topic: str, request: Request) -> JSONResponse:
    prof = _get_profile(request)
    if not prof:
        return JSONResponse(status_code=503, content={"error_key": "err.profile_unavailable"})
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
        return JSONResponse(status_code=503, content={"error_key": "err.memory_unavailable"})
    items = await mem.list_all()
    return JSONResponse(content={"memories": items, "count": len(items)})


@router.post("")
async def save_memory(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error_key": "err.memory_unavailable"})
    body     = await request.json()
    content  = body.get("content", "")
    source   = body.get("source", "manual")
    category = body.get("category", "general")
    if not content.strip():
        return JSONResponse(status_code=400, content={"error_key": "err.content_required"})
    mem_id = await mem.save(content=content, source=source, category=category, importance=0.8)
    return JSONResponse(content={"success": True, "id": mem_id})


# Las rutas fijas deben ir antes o con otro prefijo: esta captura cualquier
# segmento ("/fact" se interpretaba como un id y no se borraba nada).
@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error_key": "err.memory_unavailable"})
    await mem.delete(memory_id)
    return JSONResponse(content={"success": True})


@router.delete("")
async def clear_memory(request: Request) -> JSONResponse:
    mem = _get_memory(request)
    if not mem:
        return JSONResponse(status_code=503, content={"error_key": "err.memory_unavailable"})
    count = await mem.clear()
    return JSONResponse(content={"success": True, "deleted": count})


@router.get("/semantic")
async def semantic_status() -> JSONResponse:
    """Estado de la memoria por significado (modelo, descarga, recuerdos completados)."""
    from app.memory.semantic_setup import STATE
    return JSONResponse(dict(STATE))


# ── Memoria estilo Claude: secciones, archivos, edición e importación ──────

@router.get("/files")
async def memory_files(request: Request) -> JSONResponse:
    """Memoria agrupada: Tú, Temas, Áreas, Personas y Notas."""
    from app.memory.structure import build
    return JSONResponse(build(getattr(request.app.state, "memory_profile", None)))


@router.put("/profile/fact")
async def edit_fact(request: Request) -> JSONResponse:
    body = await request.json()
    perfil = request.app.state.memory_profile
    clave, texto = str(body.get("key") or ""), str(body.get("text") or "").strip()
    if not clave or not texto:
        return JSONResponse(status_code=400, content={"error_key": "err.invalid_request"})
    perfil.upsert_fact(clave, texto[:500])
    return JSONResponse({"ok": True})


@router.delete("/profile/fact")
async def delete_fact(request: Request, key: str) -> JSONResponse:
    perfil = request.app.state.memory_profile
    texto = (perfil.get().get("facts", {}) or {}).get(key)
    borrado = perfil.delete_fact(key)
    await _sync_store(request, [texto] if texto else [])
    return JSONResponse({"deleted": borrado})


@router.delete("/profile/file")
async def delete_file(request: Request, section: str, file: str) -> JSONResponse:
    """Borra todos los datos de un "archivo" (p. ej. Temas → Gustos)."""
    from app.memory.structure import seccion_de
    perfil = request.app.state.memory_profile
    borrados, textos = 0, []
    for clave, texto in list(perfil.get().get("facts", {}).items()):
        if seccion_de(clave) == (section, file) and perfil.delete_fact(clave):
            borrados += 1
            textos.append(texto)
    await _sync_store(request, textos)
    return JSONResponse({"deleted": borrados})


@router.post("/purge-sensitive")
async def purge_sensitive(request: Request) -> JSONResponse:
    """Al apagar "Incluir temas sensibles": se eliminan los ya guardados, del perfil
    y de la memoria por significado."""
    from app.memory.structure import es_sensible
    perfil = request.app.state.memory_profile
    store = getattr(request.app.state, "memory_store", None)
    borrados = 0
    for clave, texto in list(perfil.get().get("facts", {}).items()):
        if es_sensible(texto) and perfil.delete_fact(clave):
            borrados += 1
    fallidos = 0
    if store is not None:
        for rec in await store.list_all(limit=5000):
            if es_sensible(rec.get("content", "")):
                if await store.delete(rec["id"]):
                    borrados += 1
                else:
                    fallidos += 1
    return JSONResponse({"deleted": borrados, "failed": fallidos})


@router.get("/import-prompt")
async def import_prompt() -> JSONResponse:
    """Prompt para pedir a otro asistente lo que recuerda del usuario."""
    import os
    from app.memory.structure import IMPORT_PROMPT
    lang = (os.environ.get("ANDROMEDA_LANGUAGE") or "es")[:2]
    return JSONResponse({"prompt": IMPORT_PROMPT.get(lang, IMPORT_PROMPT["en"])})


@router.post("/import")
async def import_memory(request: Request) -> JSONResponse:
    """Importa lo que otro asistente recuerda: cada línea se clasifica con el
    extractor (nombre, gustos, proyectos…) y lo que no encaja queda como nota."""
    from app.memory.extractor import extract_memories, topic_key
    from app.memory.structure import parse_import
    body = await request.json()
    perfil = request.app.state.memory_profile
    store = getattr(request.app.state, "memory_store", None)
    guardados = 0
    for linea in parse_import(body.get("text") or ""):
        hallados = extract_memories(linea)
        if hallados:
            for contenido, categoria, tema in hallados:
                perfil.upsert_fact(topic_key(tema, contenido), contenido)
        else:
            perfil.upsert_fact(topic_key("explicit:importado", linea), linea)
        if store is not None:
            try:
                await store.save(linea, source="import", category="fact")
            except Exception:                             # noqa: BLE001
                pass
        guardados += 1
    return JSONResponse({"imported": guardados})



@router.post("/profile/file/rewrite")
async def rewrite_file(request: Request) -> JSONResponse:
    """Guarda el contenido de un tema editado a mano (una línea por dato)."""
    from app.memory.structure import replace_file
    body = await request.json()
    lineas = [l.lstrip("-*• ").strip() for l in str(body.get("text") or "").splitlines()]
    from app.memory.structure import file_lines
    antes = file_lines(request.app.state.memory_profile, str(body.get("section")), str(body.get("file")))
    n = replace_file(request.app.state.memory_profile, str(body.get("section")),
                     str(body.get("file")), [l for l in lineas if l])
    await _sync_store(request, [a for a in antes if a not in lineas])
    return JSONResponse({"facts": n})


@router.post("/profile/file/ai-edit")
async def ai_edit_file(request: Request) -> JSONResponse:
    """Como en Claude: se describe el cambio y la IA local reescribe el tema."""
    import httpx
    from app.memory.structure import edit_prompt, file_lines, parse_edit, replace_file
    from app.ollama_resolver import resolve_ollama_url
    body = await request.json()
    seccion, archivo = str(body.get("section")), str(body.get("file"))
    instruccion = str(body.get("instruction") or "").strip()[:1000]
    if not instruccion:
        return JSONResponse(status_code=400, content={"error_key": "err.invalid_request"})
    perfil = request.app.state.memory_profile
    registro = request.app.state.registry
    candidatos = registro.get_eligible_for_tier(4) or registro.fallback_specialists(4)
    modelo = candidatos[0].model_name if candidatos else None
    url = await resolve_ollama_url(request.app.state.settings.ollama_base_url)
    if not modelo or not url:
        return JSONResponse(status_code=503, content={"error_key": "err.ollama_offline"})
    actuales = file_lines(perfil, seccion, archivo)
    try:
        async with httpx.AsyncClient(trust_env=False) as c:
            r = await c.post(f"{url}/api/chat", json={
                "model": modelo, "stream": False, "keep_alive": "30m",
                "options": {"temperature": 0.2},
                "messages": [{"role": "user", "content": edit_prompt(
                    str(body.get("name") or archivo), actuales, instruccion)}],
            }, timeout=120.0)
        r.raise_for_status()
        nuevas = parse_edit((r.json().get("message") or {}).get("content", ""))
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"Edición de memoria con IA falló: {exc}")
        return JSONResponse(status_code=502, content={"error_key": "err.memory_ai_edit"})
    replace_file(perfil, seccion, archivo, nuevas)
    await _sync_store(request, [a for a in actuales if a not in nuevas])
    return JSONResponse({"lines": nuevas, "before": actuales})



async def _sync_store(request: Request, textos: list[str]) -> None:
    """Lo que se borra o reescribe en el perfil se borra también del almacén
    semántico. Antes solo desaparecía de la pantalla y se seguía recuperando."""
    store = getattr(request.app.state, "memory_store", None)
    if store is not None and textos:
        try:
            await store.delete_texts(textos)
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Sincronización con el almacén falló: {exc}")
