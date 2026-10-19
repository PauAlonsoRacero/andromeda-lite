"""
diagnostics.py — Registro de diagnóstico: qué hace Andromeda por dentro.

Nace de un problema concreto: los tests pasaban, la aplicación fallaba al
usarla, y averiguar por qué costaba varios intentos a ciegas. Este registro
anota cada decisión del pipeline —si se buscó en internet y por qué, qué prompt
recibió el modelo, qué devolvió cada motor, cuánto tardó cada paso— para que un
fallo se diagnostique mirando, no conjeturando.

Vive SOLO en memoria (nunca toca disco) y está apagado por defecto: se activa
con el interruptor del panel de diagnóstico o con ANDROMEDA_DIAGNOSTICS=1.

PRIVACIDAD: cuando está activo registra los prompts y las respuestas completas,
que es justo lo que hace falta para diagnosticar. Por eso está apagado de serie
y no se persiste nada: el registro muere al cerrar la aplicación. En modo
incógnito no se registra contenido, solo metadatos.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any

# Tope de eventos. Suficiente para reconstruir una sesión de trabajo sin que el
# registro crezca sin control: al llegar al tope se descartan los más antiguos.
_MAX_EVENTS = 2000

_lock = threading.Lock()
_events: deque[dict] = deque(maxlen=_MAX_EVENTS)
_enabled = os.environ.get("ANDROMEDA_DIAGNOSTICS", "").lower() in ("1", "true", "on")
_seq = 0


def is_enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> None:
    """Activa o desactiva el registro. Al desactivar se vacía."""
    global _enabled
    _enabled = bool(value)
    if not _enabled:
        clear()


def clear() -> None:
    with _lock:
        _events.clear()


def log(
    category: str,
    event: str,
    *,
    detail: str = "",
    data: dict[str, Any] | None = None,
    level: str = "info",
    duration_ms: float | None = None,
) -> None:
    """Anota un evento.

    Args:
        category: qué subsistema lo produce (chat, search, mcp, memory, ollama…)
        event:    qué ha pasado, en una línea
        detail:   texto largo (un prompt, una respuesta, un error)
        data:     datos estructurados para inspeccionar
        level:    info | warn | error | success
        duration_ms: cuánto tardó, si aplica
    """
    if not _enabled:
        return
    global _seq
    with _lock:
        _seq += 1
        _events.append({
            "seq": _seq,
            "ts": time.time(),
            "category": category,
            "event": event,
            "detail": detail,
            "data": data or {},
            "level": level,
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        })


def get_events(since_seq: int = 0, category: str = "", level: str = "") -> list[dict]:
    """Eventos posteriores a `since_seq`, opcionalmente filtrados."""
    with _lock:
        salida = [e for e in _events if e["seq"] > since_seq]
    if category:
        salida = [e for e in salida if e["category"] == category]
    if level:
        salida = [e for e in salida if e["level"] == level]
    return salida


def stats() -> dict:
    with _lock:
        total = len(_events)
        por_categoria: dict[str, int] = {}
        por_nivel: dict[str, int] = {}
        for e in _events:
            por_categoria[e["category"]] = por_categoria.get(e["category"], 0) + 1
            por_nivel[e["level"]] = por_nivel.get(e["level"], 0) + 1
        ultimo = _events[-1]["seq"] if _events else 0
    return {
        "enabled": _enabled,
        "total": total,
        "capacity": _MAX_EVENTS,
        "last_seq": ultimo,
        "by_category": por_categoria,
        "by_level": por_nivel,
    }


def as_text() -> str:
    """Registro completo en texto plano, para copiar o guardar en un archivo."""
    from datetime import datetime

    lineas = [
        "=" * 78,
        "ANDROMEDA — REGISTRO DE DIAGNÓSTICO",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Contiene los prompts y respuestas completos de esta sesión.",
        "Revísalo antes de compartirlo si hay algo personal.",
        "=" * 78,
        "",
    ]
    with _lock:
        eventos = list(_events)
    if not eventos:
        lineas.append("(sin eventos: ¿está activado el registro?)")
        return "\n".join(lineas)

    t0 = eventos[0]["ts"]
    for e in eventos:
        rel = e["ts"] - t0
        dur = f" [{e['duration_ms']}ms]" if e["duration_ms"] is not None else ""
        lineas.append(
            f"[{rel:8.3f}s] {e['level'].upper():7} {e['category']:10} "
            f"{e['event']}{dur}"
        )
        if e["data"]:
            for k, v in e["data"].items():
                lineas.append(f"{'':22}{k}: {v}")
        if e["detail"]:
            for linea in str(e["detail"]).split("\n"):
                lineas.append(f"{'':22}| {linea}")
        lineas.append("")
    return "\n".join(lineas)


class timed:
    """Mide un bloque y lo anota al salir.

    Uso:
        with timed("search", "búsqueda web") as t:
            resultados = await buscar()
            t.data["resultados"] = len(resultados)
    """

    def __init__(self, category: str, event: str, **kw):
        self.category, self.event, self.kw = category, event, kw
        self.data: dict[str, Any] = {}
        self.detail = ""
        self.level = "info"
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        ms = (time.perf_counter() - self._t0) * 1000
        if exc is not None:
            self.level = "error"
            self.detail = f"{exc_type.__name__}: {exc}"
        log(self.category, self.event, detail=self.detail, data=self.data,
            level=self.level, duration_ms=ms, **self.kw)
        return False        # nunca silencia la excepción
