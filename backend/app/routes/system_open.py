"""routes/system_open.py — Abrir enlaces en el navegador del sistema.

En la app de escritorio, un enlace de una respuesta se abría DENTRO de la propia
ventana (el webview), sin barra de navegación: no había forma de volver atrás
salvo cerrar la aplicación. Los enlaces externos se abren ahora en el navegador
predeterminado del usuario.
"""
from __future__ import annotations

import logging
import webbrowser
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.system_open")
router = APIRouter(prefix="/api/system", tags=["System"])


@router.post("/open-url")
async def open_url(request: Request) -> JSONResponse:
    body = await request.json()
    url = str(body.get("url") or "").strip()
    # Solo web: nunca file://, javascript: ni esquemas que ejecuten programas.
    if urlparse(url).scheme not in ("http", "https") or len(url) > 4000:
        return JSONResponse(status_code=400, content={"error_key": "err.invalid_url"})
    try:
        abierto = webbrowser.open(url, new=2)
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"No se pudo abrir el navegador: {exc}")
        abierto = False
    return JSONResponse({"opened": bool(abierto)})
