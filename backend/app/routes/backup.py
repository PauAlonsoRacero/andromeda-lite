"""
Respaldo y migración de datos (export/import) — pensado para el binario de
escritorio, donde la descarga de Blobs del navegador no funciona como en web.

  POST /api/backup/export  → escribe un .json con conversaciones + memorias en
                             la carpeta de datos del usuario y devuelve la ruta.
  POST /api/backup/import  → recibe el contenido de un backup y restaura las
                             memorias (las conversaciones las gestiona el front).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/backup", tags=["Backup"])


def _exports_dir(request: Request) -> Path:
    """Carpeta donde guardar los backups (data dir del usuario)."""
    settings = request.app.state.settings
    # memory_db_path vive en la carpeta de datos; usamos su directorio.
    base = Path(getattr(settings, "memory_db_path", "data/memory.db")).parent
    d = base / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/export")
async def export_backup(request: Request) -> JSONResponse:
    body = await request.json()
    conversations = body.get("conversations", [])
    mem = getattr(request.app.state, "memory_store", None)
    memories = []
    if mem:
        try:
            memories = await mem.list_all()
        except Exception:
            memories = []
    data = {
        "app": "andromeda",
        "version": 2,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conversations": conversations,
        "memories": memories,
    }
    fname = f"andromeda-backup-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path = _exports_dir(request) / fname
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse(content={
        "success": True,
        "path": str(path),
        "conversations": len(conversations),
        "memories": len(memories),
    })


@router.post("/import")
async def import_backup(request: Request) -> JSONResponse:
    body = await request.json()
    memories = body.get("memories", [])
    mem = getattr(request.app.state, "memory_store", None)
    added = 0
    if mem and isinstance(memories, list):
        for m in memories:
            if not isinstance(m, dict) or not m.get("content"):
                continue
            try:
                await mem.save(
                    content=m["content"],
                    source=m.get("source", "import"),
                    category=m.get("category", "general"),
                )
                added += 1
            except Exception:
                pass
    return JSONResponse(content={"success": True, "memories_imported": added})
