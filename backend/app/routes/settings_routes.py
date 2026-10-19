"""
settings_routes.py — Ajustes globales de Andromeda que el backend necesita conocer.

Por ahora: el idioma activo. La interfaz (frontend) tiene su propia i18n; aquí
guardamos el idioma para que las IAs respondan en él (vía with_identity, que lee
la variable de entorno ANDROMEDA_LANGUAGE) y lo persistimos en un fichero para
que sobreviva a reinicios.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.settings")
router = APIRouter()

VALID_LANGS = {"es", "en", "de", "zh", "fr"}


def _prefs_path() -> Path:
    base = os.environ.get("ANDROMEDA_DATA_DIR") or str(Path.home() / ".andromeda")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p / "preferences.json"


def _load_prefs() -> dict:
    try:
        return json.loads(_prefs_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        from app.core.fsutil import atomic_write_text
        atomic_write_text(_prefs_path(), json.dumps(prefs, indent=2))
    except Exception as exc:
        logger.warning(f"No se pudieron guardar las preferencias: {exc}")


def apply_saved_language() -> str:
    """Carga el idioma guardado y lo expone en ANDROMEDA_LANGUAGE. Llamar al arrancar."""
    lang = (_load_prefs().get("language") or os.environ.get("ANDROMEDA_LANGUAGE") or "en")
    lang = lang.strip().lower()[:2]
    if lang not in VALID_LANGS:
        lang = "en"
    os.environ["ANDROMEDA_LANGUAGE"] = lang

    # Instancia propia de SearXNG, si el usuario configuró una.
    searxng = (_load_prefs().get("searxng_url") or "").strip()
    if searxng:
        os.environ["ANDROMEDA_SEARXNG_URL"] = searxng

    # Retención del modelo en memoria.
    ka = (_load_prefs().get("keep_alive") or "").strip()
    if ka:
        os.environ["ANDROMEDA_KEEP_ALIVE"] = ka

    return lang


@router.get("/language")
async def get_language() -> JSONResponse:
    return JSONResponse({"language": os.environ.get("ANDROMEDA_LANGUAGE", "en")})


@router.post("/language")
async def set_language(request: Request) -> JSONResponse:
    body = await request.json()
    lang = str(body.get("language", "es")).strip().lower()[:2]
    if lang not in VALID_LANGS:
        return JSONResponse(status_code=400, content={"error": f"Idioma no soportado: {lang}"})
    os.environ["ANDROMEDA_LANGUAGE"] = lang
    prefs = _load_prefs()
    prefs["language"] = lang
    _save_prefs(prefs)
    logger.info(f"Idioma cambiado a: {lang}")
    return JSONResponse({"success": True, "language": lang})


@router.get("/searxng")
async def get_searxng() -> JSONResponse:
    """Instancia de SearXNG configurada y estado del buscador."""
    import os
    from app.core import web_search
    return JSONResponse({
        "url": os.environ.get("ANDROMEDA_SEARXNG_URL", ""),
        # Cuál está respondiendo ahora mismo, para que el usuario sepa si su
        # instancia se está usando de verdad o se cayó a una pública.
        "active": web_search._searxng_working or "",
        "public_fallbacks": len(web_search._SEARXNG_PUBLIC),
    })


@router.put("/searxng")
async def set_searxng(request: Request) -> JSONResponse:
    """Configura una instancia propia de SearXNG (o la borra para usar públicas)."""
    import os
    from app.core import web_search

    body = await request.json()
    url = (body.get("url") or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        return JSONResponse(status_code=400,
                            content={"error": "La URL debe empezar por http:// o https://"})

    prefs = _load_prefs()
    if url:
        prefs["searxng_url"] = url
        os.environ["ANDROMEDA_SEARXNG_URL"] = url
    else:
        prefs.pop("searxng_url", None)
        os.environ.pop("ANDROMEDA_SEARXNG_URL", None)
    _save_prefs(prefs)
    web_search._searxng_working = None      # olvidar la instancia recordada

    # Comprobar que responde, para no dejar al usuario con una URL que no vale.
    ok, detalle = False, ""
    if url:
        try:
            resultados = await web_search._search_searxng("test", 1, timeout=6.0)
            ok = bool(resultados)
        except Exception as exc:            # noqa: BLE001
            detalle = f"{type(exc).__name__}"
    return JSONResponse({"saved": True, "url": url, "reachable": ok, "detail": detalle})


@router.get("/keep-alive")
async def get_keep_alive() -> JSONResponse:
    """Cuánto tiempo se mantiene el modelo cargado en memoria."""
    import os
    return JSONResponse({"keep_alive": os.environ.get("ANDROMEDA_KEEP_ALIVE", "30m")})


@router.put("/keep-alive")
async def set_keep_alive(request: Request) -> JSONResponse:
    """Ajusta la retención del modelo en memoria.

    Mantenerlo cargado elimina la recarga entre mensajes (decenas de segundos
    con modelos grandes), a costa de retener VRAM. Quien necesite la memoria
    para otras cosas puede bajarlo o ponerlo a 0.
    """
    import os
    import re as _re

    body = await request.json()
    valor = str(body.get("keep_alive") or "").strip()
    # Formato de Ollama: "30m", "1h", "-1" (indefinido), "0" (descargar ya)
    if not _re.fullmatch(r"-?\d+[smh]?", valor):
        return JSONResponse(status_code=400, content={
            "error": "Formato inválido. Usa por ejemplo 30m, 1h, 0 o -1."})

    prefs = _load_prefs()
    prefs["keep_alive"] = valor
    _save_prefs(prefs)
    os.environ["ANDROMEDA_KEEP_ALIVE"] = valor
    return JSONResponse({"saved": True, "keep_alive": valor})
