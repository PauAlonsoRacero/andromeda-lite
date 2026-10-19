"""
ollama_resolver.py — Detecta automáticamente la URL de Ollama que funciona.

Problema: en Docker Desktop (Windows/Mac), Ollama corre en el HOST y el backend
puede llegar por varias rutas. En la app de escritorio corre nativo en localhost.
Este módulo prueba varias hasta encontrar una.

IMPORTANTE (bug Windows): la detección usa la librería ESTÁNDAR (urllib), no
httpx. Motivo: en el .exe empaquetado con PyInstaller, si falta cualquier
dependencia oculta de httpx (httpcore/h11/certifi), toda llamada httpx falla en
silencio y Ollama parece "no detectado" aunque esté corriendo. urllib siempre se
empaqueta (es stdlib), así que la detección es fiable en el binario.
"""
import asyncio
import json
import logging
import urllib.request

logger = logging.getLogger("andromeda.ollama")

# URLs candidatas en orden de preferencia.
# En Windows 'localhost' puede resolver IPv6 (::1) mientras Ollama escucha en
# IPv4 → 127.0.0.1 primero para garantizar IPv4.
CANDIDATE_URLS = [
    "http://127.0.0.1:11434",              # app nativa Windows/Mac (IPv4 explícito)
    "http://localhost:11434",              # app nativa (alias)
    "http://host.docker.internal:11434",   # Docker Desktop Windows/Mac
    "http://172.17.0.1:11434",             # Docker bridge gateway (Linux)
    "http://gateway.docker.internal:11434",# algunas versiones de Docker
]

_resolved_url: str | None = None
# Opener que IGNORA proxies del sistema (clave en Windows con VPN/proxy: si no,
# las peticiones a localhost se enrutan por el proxy y fallan).
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe_sync(url: str, timeout: float = 2.5) -> dict | None:
    """Comprueba /api/tags con urllib (stdlib). Devuelve el JSON o None.

    Síncrono a propósito: lo llamamos vía asyncio.to_thread para no bloquear el
    event loop. Bulletproof en el .exe (no depende de httpx).
    """
    try:
        req = urllib.request.Request(
            f"{url}/api/tags",
            headers={"User-Agent": "andromeda", "Accept": "application/json"},
        )
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _default_timeout() -> float:
    """Timeout al sondear Ollama.

    En los tests no hay Ollama, así que cada sondeo agota su tiempo completo y
    el arranque de la aplicación tardaba ~2,6 s. Con 300 tests que crean la app,
    eso son minutos de espera pura. En producción se mantiene el margen amplio
    porque Ollama puede tardar en responder si está cargando un modelo.
    """
    import os
    if os.environ.get("ANDROMEDA_ENVIRONMENT") == "test":
        return 0.25
    return 2.5


async def _probe(url: str, timeout: float | None = None) -> dict | None:
    return await asyncio.to_thread(probe_sync, url, timeout or _default_timeout())


# Cuándo se comprobó por última vez sin éxito. Sin esto, cada llamada reprueba
# TODAS las URLs candidatas: con Ollama apagado eso son ~260 ms por petición, y
# la interfaz consulta el estado cada 3 segundos.
_last_failure: float = 0.0
_FAILURE_CACHE_S = 5.0


async def resolve_ollama_url(preferred: str | None = None) -> str | None:
    """Devuelve la primera URL de Ollama que responde a /api/tags.

    Si la última búsqueda falló hace poco, se devuelve None sin volver a
    sondear: Ollama no aparece de un segundo a otro, y reprobar en cada
    petición hace que toda la interfaz vaya lenta cuando está apagado.
    """
    global _resolved_url, _last_failure

    import time as _t
    # Si la última búsqueda falló hace menos de _FAILURE_CACHE_S, no se vuelve a
    # sondear: Ollama no aparece de un segundo a otro, y reprobar todas las URLs
    # en cada petición hace que la interfaz vaya lenta cuando está apagado.
    # `reset_cache()` la invalida cuando el usuario cambia la configuración.
    if not _resolved_url and (_t.monotonic() - _last_failure) < _FAILURE_CACHE_S:
        return None

    urls = []
    if _resolved_url:
        urls.append(_resolved_url)
    if preferred and preferred not in urls:
        urls.append(preferred)
    urls += [u for u in CANDIDATE_URLS if u not in urls]

    for url in urls:
        if await _probe(url) is not None:
            if _resolved_url != url:
                logger.info(f"Ollama encontrado en: {url}")
            _resolved_url = url
            return url

    _resolved_url = None
    _last_failure = _t.monotonic()
    logger.warning("Ollama no encontrado en ninguna URL candidata")
    return None


async def resolve_with_models(preferred: str | None = None) -> tuple[str | None, list[str]]:
    """Como resolve_ollama_url pero además devuelve la lista de modelos instalados,
    en una sola pasada (evita una segunda petición)."""
    global _resolved_url
    urls = []
    if _resolved_url:
        urls.append(_resolved_url)
    if preferred and preferred not in urls:
        urls.append(preferred)
    urls += [u for u in CANDIDATE_URLS if u not in urls]

    for url in urls:
        data = await _probe(url)
        if data is not None:
            _resolved_url = url
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return url, models
    _resolved_url = None
    return None, []


def get_cached_url() -> str | None:
    return _resolved_url


def reset_cache() -> None:
    """Olvida la URL resuelta y el último fallo.

    Necesario cuando cambia la configuración de Ollama o entre pruebas: sin
    esto, un fallo cacheado hace que no se detecte un servidor que sí está.
    """
    global _resolved_url, _last_failure
    _resolved_url = None
    _last_failure = 0.0
