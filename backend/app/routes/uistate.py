"""
Estado de UI persistente en disco (clave-valor).

En el binario de escritorio (pywebview/WKWebView en macOS) localStorage NO
persiste de forma fiable entre arranques. Para que el tema, el idioma, la IA
configurada y las conversaciones se mantengan, los guardamos en el backend,
que escribe en la carpeta de datos del usuario (Application Support/Andromeda).

  GET  /api/uistate            → devuelve todo el estado guardado (dict)
  GET  /api/uistate/{key}      → devuelve un valor
  PUT  /api/uistate/{key}      → guarda un valor  (body: {"value": <any>})
  DELETE /api/uistate/{key}    → borra un valor
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/uistate", tags=["UIState"])
_lock = threading.Lock()


def _state_path(request: Request) -> Path:
    settings = request.app.state.settings
    base = Path(getattr(settings, "memory_db_path", "data/memory.db")).parent
    base.mkdir(parents=True, exist_ok=True)
    return base / "ui_state.json"


def _load(request: Request) -> dict:
    p = _state_path(request)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(request: Request, data: dict) -> None:
    p = _state_path(request)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)  # escritura atómica


@router.get("")
async def get_all(request: Request) -> JSONResponse:
    with _lock:
        return JSONResponse(content={"state": _load(request)})


@router.get("/{key}")
async def get_one(key: str, request: Request) -> JSONResponse:
    with _lock:
        data = _load(request)
    return JSONResponse(content={"key": key, "value": data.get(key)})


@router.put("/{key}")
async def put_one(key: str, request: Request) -> JSONResponse:
    body = await request.json()
    value = body.get("value")
    with _lock:
        data = _load(request)
        data[key] = value
        _save(request, data)
    return JSONResponse(content={"key": key, "value": value, "success": True})


@router.delete("/{key}")
async def delete_one(key: str, request: Request) -> JSONResponse:
    with _lock:
        data = _load(request)
        data.pop(key, None)
        _save(request, data)
    return JSONResponse(content={"key": key, "success": True})
