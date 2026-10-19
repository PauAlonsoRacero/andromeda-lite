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
            return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
        ext = abs_path.suffix.lstrip(".").lower()
        media = _MIME.get(ext, "application/octet-stream")
        filename = abs_path.name
        # Sin caché: el visor carga siempre la misma URL, y el navegador servía
        # la primera versión del archivo aunque se hubiera modificado ("la página
        # se ve igual" cuando sí había cambiado).
        headers = {"Cache-Control": "no-store, max-age=0"}
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
            "error_key": "err.delete_needs_confirm",
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



# Sandbox impuesto por el servidor: aunque la página se abra directamente, su
# origen queda aislado y sus scripts no pueden llamar a la API de Andromeda.
_SANDBOX = {"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups",
            "Cache-Control": "no-store, max-age=0"}


@router.get("/view/{path:path}")
async def view(path: str):
    """Vista previa por ruta real.

    Servir la página como /view/web/index.html (y no /raw?path=…) hace que sus
    recursos relativos —estilo.css, app.js, imágenes— se resuelvan bien. Word,
    Excel y CSV se convierten a HTML para poder verse.
    """
    from pathlib import Path as _P
    from fastapi.responses import HTMLResponse
    from app.core.doc_preview import CONVERTIBLES
    try:
        abs_path = _resolve_inside(get_workspace_root(), path)
    except WorkspaceError:
        return JSONResponse(status_code=400, content={"error_key": "err.invalid_path"})
    if not abs_path.is_file():
        return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
    conv = CONVERTIBLES.get(_P(abs_path).suffix.lower())
    if conv:
        try:
            return HTMLResponse(conv(abs_path), headers=_SANDBOX)
        except Exception as exc:                          # noqa: BLE001
            logger.warning(f"No se pudo convertir {path}: {exc}")
            return JSONResponse(status_code=422, content={"error_key": "err.preview_failed"})
    return FileResponse(str(abs_path), headers=_SANDBOX)


@router.post("/export")
async def export_to_downloads(request: Request) -> JSONResponse:
    """Copia un archivo a la carpeta Descargas del usuario.

    En la app de escritorio (pywebview) los enlaces de descarga no hacen nada:
    los botones "Descargar" de Artefactos y de la vista previa no funcionaban
    con Word, PDF o Excel. Se copia desde el propio backend.
    """
    import shutil
    from pathlib import Path as _P
    body = await request.json()
    rel = str(body.get("path") or "")
    pid = body.get("project_id")
    try:
        if pid:
            from app.core import projects as pj
            origen = pj._inside(pj.project_root(pid), rel)
        else:
            origen = _resolve_inside(get_workspace_root(), rel)
    except Exception:                                     # noqa: BLE001
        return JSONResponse(status_code=400, content={"error_key": "err.invalid_path"})
    if not origen.is_file():
        return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
    descargas = _P.home() / "Downloads"
    descargas.mkdir(parents=True, exist_ok=True)
    destino = descargas / origen.name
    n = 1
    while destino.exists():                               # no pisar archivos existentes
        destino = descargas / f"{origen.stem} ({n}){origen.suffix}"
        n += 1
    shutil.copy2(origen, destino)
    return JSONResponse({"saved": str(destino), "name": destino.name})
