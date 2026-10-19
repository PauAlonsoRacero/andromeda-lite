"""
routes/chat_jobs.py — Respuestas progresivas para la app de escritorio.

El escritorio no puede leer una respuesta a trozos: en macOS, WKWebView no
entrega el cuerpo de una petición fetch de forma incremental. Por eso pedía la
respuesta entera y la pintaba de golpe tras 15-30 segundos de espera muda.

Aquí la respuesta se genera en streaming en el propio backend (el mismo camino
que usa el navegador, con todas sus capacidades) y se va acumulando en un
"trabajo" en memoria. La interfaz consulta ese trabajo cada ~100 ms y recibe
solo el texto nuevo y la fase actual (buscando, pensando, escribiendo). El
resultado es el mismo efecto de escritura progresiva, y funciona en cualquier
webview porque solo usa peticiones normales.

Efecto secundario deseable: el escritorio deja de ir por un camino distinto del
navegador. Mantener dos caminos es lo que provocó que la búsqueda web y la
creación de archivos no existieran en escritorio durante semanas.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.chat_jobs")
router = APIRouter(prefix="/api/chat/jobs", tags=["Chat"])

_jobs: dict[str, dict] = {}
_TTL_S = 600            # un trabajo olvidado se descarta a los 10 minutos


def _purge() -> None:
    limite = time.time() - _TTL_S
    for jid in [j for j, d in _jobs.items() if d["ts"] < limite]:
        tarea = _jobs[jid].get("task")
        if tarea and not tarea.done():
            tarea.cancel()
        _jobs.pop(jid, None)


def _transport_for(request: Request):
    """Cliente hacia el propio backend.

    En producción se usa la conexión real de loopback, que sí transmite a
    trozos. En los tests no hay servidor escuchando (TestClient), así que se
    llama a la aplicación directamente.
    """
    if request.url.hostname == "testserver":
        return httpx.ASGITransport(app=request.app), "http://testserver"
    return None, str(request.base_url).rstrip("/")


async def _run(job: dict, request: Request, body: dict, headers: dict) -> None:
    transport, base = _transport_for(request)
    try:
        # timeout=None a propósito: una respuesta del modelo local puede tardar minutos.
        async with httpx.AsyncClient(transport=transport, timeout=None,  # nosec B113
                                     trust_env=False) as client:
            async with client.stream("POST", f"{base}/api/chat",
                                     json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    texto = (await resp.aread()).decode("utf-8", "replace")
                    try:
                        job["error"] = json.loads(texto)
                    except ValueError:
                        job["error"] = {"message": f"HTTP {resp.status_code}"}
                    return
                async for linea in resp.aiter_lines():
                    if not linea.startswith("data: "):
                        continue
                    dato = linea[6:].strip()
                    if dato == "[DONE]":
                        break
                    try:
                        chunk = json.loads(dato)
                    except ValueError:
                        continue
                    meta = chunk.get("metadata") or {}
                    if chunk.get("is_final"):
                        if meta.get("error"):
                            job["error"] = {"message": chunk.get("content") or "error"}
                        job["meta"] = meta
                    elif meta.get("phase"):
                        job["phase"] = meta["phase"]
                    elif meta.get("placeholder"):
                        job["phrase"] = meta["placeholder"]
                        job["phase"] = "thinking"
                    elif chunk.get("content"):
                        job["text"] += chunk["content"]
                        job["phase"] = "writing"
                        job["specialist"] = chunk.get("specialist_id")
                    job["ts"] = time.time()
    except asyncio.CancelledError:
        job["error"] = {"message": "cancelled"}
        raise
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"Trabajo de chat falló: {exc}")
        job["error"] = {"message": str(exc)}
    finally:
        job["done"] = True


@router.post("")
async def start(request: Request) -> JSONResponse:
    """Arranca una respuesta y devuelve el id para consultar su progreso."""
    _purge()
    body = await request.json()
    body["stream"] = True
    headers = {"Content-Type": "application/json"}
    # Marca de llamada interna: el limitador no la cuenta dos veces.
    interno = getattr(request.app.state, "internal_token", None)
    if interno:
        headers["X-Andromeda-Internal"] = interno
    token = request.headers.get("X-Andromeda-Token")
    if token:
        headers["X-Andromeda-Token"] = token

    job_id = str(uuid.uuid4())
    job = {"text": "", "phase": "thinking", "phrase": None, "specialist": None,
           "meta": None, "error": None, "done": False, "ts": time.time()}
    _jobs[job_id] = job
    job["task"] = asyncio.create_task(_run(job, request, body, headers))
    return JSONResponse({"job_id": job_id})


@router.get("/{job_id}")
async def poll(job_id: str, since: int = 0) -> JSONResponse:
    """Texto nuevo desde `since`, fase actual y, al terminar, los metadatos."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error_key": "err.not_found"})
    since = max(0, min(since, len(job["text"])))
    respuesta = {
        "delta": job["text"][since:],
        "offset": len(job["text"]),
        "phase": job["phase"],
        "phrase": job["phrase"],
        "specialist": job["specialist"],
        "done": job["done"],
    }
    if job["done"]:
        respuesta["meta"] = job["meta"] or {}
        respuesta["error"] = job["error"]
        # Una vez entregado el final, el trabajo ya no hace falta.
        if since >= len(job["text"]):
            _jobs.pop(job_id, None)
    return JSONResponse(respuesta)


@router.delete("/{job_id}")
async def cancel(job_id: str) -> JSONResponse:
    """Detiene la generación (botón de parar)."""
    job = _jobs.pop(job_id, None)
    if job and job.get("task") and not job["task"].done():
        job["task"].cancel()
    return JSONResponse({"cancelled": job is not None})
