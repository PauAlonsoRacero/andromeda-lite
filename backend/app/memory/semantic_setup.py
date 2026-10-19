"""
semantic_setup.py — Memoria por significado, lista sin que el usuario haga nada.

La búsqueda semántica (encontrar "me gusta el Audi TT" al preguntar "¿qué coche
me gustaba?", sin palabras en común) necesita un modelo de embeddings en Ollama.
Antes había que instalarlo a mano (`ollama pull nomic-embed-text`); sin él la
memoria buscaba solo por coincidencia de palabras, sin que nadie lo supiera.

Ahora, al arrancar:
  1. se comprueba si el modelo está instalado;
  2. si no, se descarga en segundo plano (~270 MB), sin bloquear el chat;
  3. al terminar, se calculan los vectores de los recuerdos que ya existían.

Si Ollama aún no está abierto, se reintenta periodicamente. Si el usuario ha
desactivado el acceso a la red en Capacidades, no se descarga nada.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.memory.store import EMBED_MODEL

logger = logging.getLogger("andromeda.memory.semantic")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:
        @staticmethod
        def log(*a, **k): pass
    diag = _Nulo()

# Estado visible en Ajustes → Memoria y en Diagnóstico.
STATE: dict = {"model": EMBED_MODEL, "status": "pending", "progress": 0,
               "backfilled": 0, "error": ""}


def _instalado(nombres: list[str]) -> bool:
    return any(n == EMBED_MODEL or n.split(":")[0] == EMBED_MODEL for n in nombres)


async def _descargar(client: httpx.AsyncClient, url: str) -> None:
    STATE.update(status="downloading", progress=0)
    diag.log("memory", f"descargando {EMBED_MODEL} para la memoria por significado")
    async with client.stream("POST", f"{url}/api/pull",
                             json={"model": EMBED_MODEL, "stream": True},
                             timeout=httpx.Timeout(None, connect=10)) as r:
        r.raise_for_status()
        async for linea in r.aiter_lines():
            if not linea.strip():
                continue
            try:
                dato = json.loads(linea)
            except ValueError:
                continue
            if dato.get("error"):
                raise RuntimeError(dato["error"])
            total, hecho = dato.get("total"), dato.get("completed")
            if total and hecho:
                STATE["progress"] = min(99, int(hecho * 100 / total))


async def ensure_semantic_memory(settings, store, *, intentos: int = 40,
                                 espera_s: float = 30.0) -> None:
    """Deja la memoria semántica operativa. Pensado para lanzarse con spawn()."""
    if store is None:
        return
    # Higiene: la limpieza de datos basura o contradictorios ("me gusta el negro?
    # lo odio") existía para el perfil pero no para este almacén, que conservaba
    # lo que se guardó antes de corregir el extractor.
    try:
        from app.memory.profile import _es_basura
        n = await store.purge(_es_basura)
        if n:
            logger.info(f"Memoria semántica: {n} recuerdos basura eliminados")
            diag.log("memory", f"{n} recuerdos basura eliminados del almacén", level="success")
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Limpieza del almacén falló: {exc}")
    from app.core.flags import get_flag
    from app.ollama_resolver import resolve_ollama_url

    for intento in range(intentos):
        url = await resolve_ollama_url(settings.ollama_base_url)
        if not url:
            STATE.update(status="waiting_ollama")
            await asyncio.sleep(espera_s)
            continue
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                r = await client.get(f"{url}/api/tags", timeout=5.0)
                r.raise_for_status()
                nombres = [m.get("name", "") for m in r.json().get("models", [])]
                if not _instalado(nombres):
                    if not get_flag(settings, "andromeda_network_egress"):
                        STATE.update(status="offline",
                                     error="acceso a la red desactivado en Capacidades")
                        return
                    await _descargar(client, url)
            STATE.update(status="ready", progress=100, error="")
            store.ollama_url = url
            store._embed_off_until = 0.0          # dejar de usar solo palabras clave
            store.ensure_embed_scheme()           # recalcular si cambió el modo
            n = await store.backfill_embeddings()
            STATE["backfilled"] = n
            diag.log("memory", f"memoria por significado activa ({n} recuerdos vectorizados)",
                     level="success")
            logger.info(f"Memoria semántica lista con {EMBED_MODEL}; {n} recuerdos completados")
            return
        except Exception as exc:                          # noqa: BLE001
            STATE.update(status="error", error=str(exc)[:200])
            logger.warning(f"Memoria semántica: intento {intento + 1} falló: {exc}")
            await asyncio.sleep(espera_s)
