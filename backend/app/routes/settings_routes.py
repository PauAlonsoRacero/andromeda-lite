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
        _prefs_path().write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"No se pudieron guardar las preferencias: {exc}")


def apply_saved_language() -> str:
    """Carga el idioma guardado y lo expone en ANDROMEDA_LANGUAGE. Llamar al arrancar."""
    lang = (_load_prefs().get("language") or os.environ.get("ANDROMEDA_LANGUAGE") or "es")
    lang = lang.strip().lower()[:2]
    if lang not in VALID_LANGS:
        lang = "es"
    os.environ["ANDROMEDA_LANGUAGE"] = lang
    return lang


@router.get("/language")
async def get_language() -> JSONResponse:
    return JSONResponse({"language": os.environ.get("ANDROMEDA_LANGUAGE", "es")})


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
