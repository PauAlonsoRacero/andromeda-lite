"""routes/projects.py — Archivos y carpetas de cada proyecto."""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from app.core import projects as pj

logger = logging.getLogger("andromeda.routes.projects")
router = APIRouter(prefix="/api/projects", tags=["Projects"])


def _err(exc: Exception, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error_key": "err.project_file",
                                                   "message": str(exc)})


@router.get("/{project_id}/files")
async def list_files(project_id: str) -> JSONResponse:
    try:
        return JSONResponse({"files": pj.list_files(project_id)})
    except pj.ProjectError as exc:
        return _err(exc)


@router.post("/{project_id}/files")
async def upload(project_id: str, request: Request) -> JSONResponse:
    """Sube uno o varios archivos: {"files": [{"path": "carpeta/a.py", "content_b64": "…"}]}.

    La interfaz manda las rutas relativas de una carpeta completa, así que la
    estructura de subcarpetas se conserva.
    """
    body = await request.json()
    guardados, errores = [], []
    for f in (body.get("files") or [])[:500]:
        try:
            datos = base64.b64decode(f.get("content_b64") or "", validate=False)
            guardados.append(pj.save_file(project_id, f.get("path") or "", datos))
        except (pj.ProjectError, ValueError, OSError) as exc:
            errores.append({"path": f.get("path"), "error": str(exc)})
    return JSONResponse({"saved": guardados, "errors": errores,
                         "files": pj.list_files(project_id) if guardados else None})


@router.delete("/{project_id}/files")
async def delete(project_id: str, path: str) -> JSONResponse:
    try:
        return JSONResponse({"deleted": pj.delete_path(project_id, path),
                             "files": pj.list_files(project_id)})
    except pj.ProjectError as exc:
        return _err(exc)


@router.get("/{project_id}/files/raw")
async def raw(project_id: str, path: str):
    try:
        destino = pj._inside(pj.project_root(project_id), path)
    except pj.ProjectError as exc:
        return _err(exc)
    if not destino.is_file():
        return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
    return FileResponse(str(destino), headers={"Cache-Control": "no-store"})


@router.get("/{project_id}/view/{path:path}")
async def view(project_id: str, path: str):
    """Vista previa de un archivo del proyecto (igual que /api/files/view)."""
    from pathlib import Path as _P
    from fastapi.responses import HTMLResponse
    from app.core.doc_preview import CONVERTIBLES
    cabeceras = {"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups",
                 "Cache-Control": "no-store, max-age=0"}
    try:
        destino = pj._inside(pj.project_root(project_id), path)
    except pj.ProjectError as exc:
        return _err(exc)
    if not destino.is_file():
        return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
    conv = CONVERTIBLES.get(_P(destino).suffix.lower())
    if conv:
        try:
            return HTMLResponse(conv(destino), headers=cabeceras)
        except Exception as exc:                          # noqa: BLE001
            logger.warning(f"No se pudo convertir {path}: {exc}")
            return JSONResponse(status_code=422, content={"error_key": "err.preview_failed"})
    return FileResponse(str(destino), headers=cabeceras)
