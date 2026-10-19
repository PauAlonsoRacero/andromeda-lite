"""
rag.py — RAG local de Andromeda Pro.

  POST   /api/rag/documents      → indexar {id, text, meta?}
  GET    /api/rag/query?q=&k=    → top-k chunks relevantes
  DELETE /api/rag/documents/{id} → des-indexar
  GET    /api/rag/stats          → tamaño del índice
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def _index(request: Request):
    return getattr(request.app.state, "rag_index", None)


@router.post("/documents")
async def index_document(request: Request) -> JSONResponse:
    idx = _index(request)
    if idx is None:
        return JSONResponse(status_code=503, content={"error": "RAG no disponible"})
    body = await request.json()
    doc_id = (body.get("id") or "").strip()
    text = body.get("text") or ""
    if not doc_id or not text.strip():
        return JSONResponse(status_code=400, content={"error": "Se requiere 'id' y 'text'"})
    n = idx.add_document(doc_id, text, meta=body.get("meta") or {})
    return JSONResponse(content={"indexed": True, "chunks": n, **idx.stats()})


@router.get("/query")
async def query(request: Request, q: str = "", k: int = 4) -> JSONResponse:
    idx = _index(request)
    if idx is None:
        return JSONResponse(status_code=503, content={"error": "RAG no disponible"})
    hits = idx.query(q, k=max(1, min(int(k or 4), 10)))
    return JSONResponse(content={"query": q, "results": [
        {"id": h["id"], "doc_id": h["doc_id"], "score": h["score"],
         "text": h["text"], "meta": h.get("meta", {})} for h in hits]})


@router.delete("/documents/{doc_id}")
async def remove(request: Request, doc_id: str) -> JSONResponse:
    idx = _index(request)
    if idx is None:
        return JSONResponse(status_code=503, content={"error": "RAG no disponible"})
    n = idx.remove_document(doc_id)
    return JSONResponse(content={"removed_chunks": n, **idx.stats()})


@router.get("/stats")
async def stats(request: Request) -> JSONResponse:
    idx = _index(request)
    if idx is None:
        return JSONResponse(status_code=503, content={"error": "RAG no disponible"})
    return JSONResponse(content=idx.stats())


@router.get("/documents")
async def list_documents(request: Request) -> JSONResponse:
    """Lista de documentos indexados con nº de chunks y metadatos."""
    idx = _index(request)
    if idx is None:
        return JSONResponse(status_code=503, content={"error": "RAG no disponible"})
    docs: dict[str, dict] = {}
    for c in idx.chunks:
        d = docs.setdefault(c["doc_id"], {"id": c["doc_id"], "chunks": 0,
                                          "meta": c.get("meta") or {}})
        d["chunks"] += 1
    return JSONResponse(content={"documents": sorted(docs.values(), key=lambda d: d["id"])})
