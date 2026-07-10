"""
Comprobación de actualizaciones.

  GET /api/updates/check  → compara la versión local con la última release
                            publicada en GitHub. No envía ningún dato del
                            usuario; solo hace una petición de lectura a la
                            API pública de GitHub. Falla en silencio si no
                            hay conexión (Andromeda funciona igual sin esto).

La versión local se lee de settings.app_version. El repositorio se configura
con ANDROMEDA_GITHUB_REPO (por defecto el repo público de Lite).
"""
from __future__ import annotations

import os
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.updates")
router = APIRouter(prefix="/api/updates", tags=["Updates"])

GITHUB_REPO = os.environ.get("ANDROMEDA_GITHUB_REPO", "PauAlonsoRacero/andromeda-lite")
_TIMEOUT = 4.0


def _parse_version(v: str) -> tuple[int, ...]:
    """Convierte 'v2.12.0' o '2.12.0' en (2, 12, 0) para comparar."""
    v = (v or "").lstrip("vV").strip()
    parts = []
    for chunk in v.split("."):
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


@router.get("/check")
async def check_updates(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    current = getattr(settings, "app_version", "0.0.0")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(url, headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            # Sin releases todavía, repo privado, o rate limit: no es un error.
            return JSONResponse(content={
                "update_available": False,
                "current": current,
                "checked": True,
                "reason": "no_release",
            })
        data = r.json()
        latest = data.get("tag_name") or data.get("name") or ""
        available = _parse_version(latest) > _parse_version(current)
        return JSONResponse(content={
            "update_available": available,
            "current": current,
            "latest": latest.lstrip("vV"),
            "url": data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest"),
            "notes": (data.get("body") or "")[:500],
            "checked": True,
        })
    except Exception as e:
        logger.debug(f"No se pudo comprobar actualizaciones: {e}")
        # Falla en silencio: la app funciona igual sin conexión.
        return JSONResponse(content={
            "update_available": False,
            "current": current,
            "checked": False,
        })
