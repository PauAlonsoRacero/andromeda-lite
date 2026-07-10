"""
Rutas del workspace de archivos de Andromeda.

Exponen el acceso al sistema de archivos local (crear / leer / modificar /
borrar / mover) de forma segura. El borrado es reversible por defecto
(papelera). Todas las operaciones quedan confinadas al workspace.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from app.core.workspace import Workspace, WorkspaceError, get_workspace_root, _resolve_inside

logger = logging.getLogger("andromeda.files")
router = APIRouter()

# Content-types para servir/renderizar artefactos directamente en el navegador.
_MIME = {
    "html": "text/html", "htm": "text/html", "css": "text/css",
    "js": "application/javascript", "json": "application/json",
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv",
    "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
    "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _ws() -> Workspace:
    return Workspace(root=get_workspace_root())


@router.get("/root")
async def workspace_root(request: Request) -> JSONResponse:
    """Devuelve la ruta del workspace actual."""
    return JSONResponse({"root": str(get_workspace_root())})


@router.get("/list")
async def list_files(request: Request) -> JSONResponse:
    """Lista archivos y carpetas. Query opcional: ?path=subcarpeta"""
    subpath = request.query_params.get("path", "")
    try:
        items = _ws().list(subpath)
        return JSONResponse({"files": [i.to_dict() for i in items]})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/read")
async def read_file(request: Request) -> JSONResponse:
    """Lee un archivo de texto. Query: ?path=archivo.txt"""
    path = request.query_params.get("path", "")
    try:
        content = _ws().read(path)
        return JSONResponse({"path": path, "content": content})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/raw")
async def raw_file(request: Request):
    """Sirve el archivo con su content-type real para PREVISUALIZARLO
    (HTML renderizado, imágenes, PDF) o DESCARGARLO (?download=1).

    Esto es lo que da sentido al panel de Artefactos: un HTML generado se ve
    renderizado en un iframe, no como código en crudo.
    """
    path = request.query_params.get("path", "")
    download = request.query_params.get("download") in ("1", "true", "yes")
    try:
        root = get_workspace_root()
        abs_path = _resolve_inside(root, path)
        if not abs_path.exists() or not abs_path.is_file():
            return JSONResponse(status_code=404, content={"error": "No encontrado"})
        ext = abs_path.suffix.lstrip(".").lower()
        media = _MIME.get(ext, "application/octet-stream")
        filename = abs_path.name
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return FileResponse(str(abs_path), media_type=media, headers=headers)
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/write")
async def write_file(request: Request) -> JSONResponse:
    """
    Crea o modifica un archivo.
    Body: {"path": "carpeta/archivo.txt", "content": "...", "overwrite": true}
    """
    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")
    overwrite = bool(body.get("overwrite", True))
    try:
        info = _ws().write(path, content, overwrite=overwrite)
        logger.info(f"write: {info.path} ({info.size} bytes)")
        return JSONResponse({"success": True, "file": info.to_dict()})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/mkdir")
async def make_dir(request: Request) -> JSONResponse:
    """Crea una carpeta. Body: {"path": "nueva/carpeta"}"""
    body = await request.json()
    try:
        info = _ws().mkdir(body.get("path", ""))
        return JSONResponse({"success": True, "dir": info.to_dict()})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/move")
async def move_file(request: Request) -> JSONResponse:
    """Mueve/renombra. Body: {"src": "a.txt", "dst": "b.txt"}"""
    body = await request.json()
    try:
        info = _ws().move(body.get("src", ""), body.get("dst", ""))
        return JSONResponse({"success": True, "file": info.to_dict()})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/delete")
async def delete_file(request: Request) -> JSONResponse:
    """
    Borra un archivo o carpeta.
    Body: {"path": "archivo.txt", "permanent": false}

    Por defecto (permanent=false) es REVERSIBLE: el elemento va a una papelera
    interna. permanent=true borra de verdad y requiere confirm=true.
    """
    body = await request.json()
    path = body.get("path", "")
    permanent = bool(body.get("permanent", False))
    if permanent and not bool(body.get("confirm", False)):
        return JSONResponse(status_code=400, content={
            "error": "el borrado permanente requiere confirm=true",
        })
    try:
        result = _ws().delete(path, permanent=permanent)
        logger.info(f"delete: {path} (permanent={permanent})")
        return JSONResponse({"success": True, **result})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/restore")
async def restore_file(request: Request) -> JSONResponse:
    """Restaura de la papelera. Body: {"trash_id": "...", "dest": "opcional"}"""
    body = await request.json()
    try:
        info = _ws().restore(body.get("trash_id", ""), body.get("dest"))
        return JSONResponse({"success": True, "file": info.to_dict()})
    except WorkspaceError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
