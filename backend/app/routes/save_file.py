"""
save_file.py — Guardado de archivos en el disco del usuario.

En una app de escritorio (pywebview) el truco habitual del navegador para
descargar —crear un blob y hacer click en un <a download>— no funciona: no hay
gestor de descargas, así que la ventana NAVEGA al contenido del blob y el
usuario se queda atrapado en una página de texto sin forma de volver atrás.

La solución correcta aquí es que el backend escriba el archivo en la carpeta de
Descargas del usuario y devuelva la ruta, que es lo que espera alguien usando
una aplicación de escritorio.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.save")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()

router = APIRouter()

_MAX_BYTES = 20 * 1024 * 1024      # 20 MB: suficiente para texto y documentos
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")
_MAX_NAME_BYTES = 200      # margen bajo el límite de 255 del sistema de ficheros


def _downloads_dir() -> Path:
    """Carpeta de descargas del usuario, con alternativas si no existe."""
    home = Path.home()
    for candidate in (home / "Downloads", home / "Descargas", home / "Téléchargements"):
        if candidate.is_dir():
            return candidate
    fallback = home / "Downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _unique_path(folder: Path, filename: str) -> Path:
    """Evita sobrescribir: archivo.md, archivo-1.md, archivo-2.md…"""
    path = folder / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 1000):
        alt = folder / f"{stem}-{i}{suffix}"
        if not alt.exists():
            return alt
    return folder / f"{stem}-{int(time.time())}{suffix}"


@router.post("")
async def save_file(request: Request) -> JSONResponse:
    """Guarda contenido de texto en la carpeta de Descargas.

    Body: {"filename": "respuesta.md", "content": "..."}
    """
    body = await request.json()
    content = body.get("content")
    if not isinstance(content, str) or not content:
        return JSONResponse(status_code=400, content={"error_key": "err.empty_content"})
    if len(content.encode("utf-8")) > _MAX_BYTES:
        return JSONResponse(status_code=413, content={"error": "El archivo es demasiado grande"})

    # Nombre saneado: solo el nombre base, nunca una ruta (evita path traversal).
    raw_name = (body.get("filename") or "andromeda.txt").strip()
    # Los acentos y la ñ se translitera a ASCII en vez de convertirse en guiones:
    # "informe_año.md" debe seguir siendo legible, no "informe_a-o.md".
    import unicodedata
    base = unicodedata.normalize("NFKD", Path(raw_name).name)
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    name = _SAFE_NAME.sub("-", base).strip(".-") or "andromeda.txt"
    if not name or name in (".", ".."):
        name = "andromeda.txt"

    # Los sistemas de ficheros rechazan nombres de más de 255 bytes. Se recorta
    # el tronco conservando la extensión, que es lo que determina con qué
    # aplicación se abrirá el archivo.
    if len(name.encode("utf-8")) > _MAX_NAME_BYTES:
        stem, dot, ext = name.rpartition(".")
        ext = f".{ext}" if dot and len(ext) <= 12 else ""
        stem = stem if dot else name
        keep = _MAX_NAME_BYTES - len(ext.encode("utf-8"))
        stem = stem.encode("utf-8")[:keep].decode("utf-8", "ignore")
        name = f"{stem}{ext}" or "andromeda.txt"

    try:
        target = _unique_path(_downloads_dir(), name)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning(f"No se pudo guardar '{name}': {exc}")
        return JSONResponse(status_code=500, content={"error": f"No se pudo guardar: {exc}"})

    logger.info(f"Archivo guardado: {target}")
    return JSONResponse(content={"saved": True, "path": str(target), "name": target.name})
