"""
background.py — Tareas en segundo plano que no desaparecen a mitad.

asyncio.create_task() solo guarda una referencia DÉBIL a la tarea. Si nadie
más la conserva, el recolector de basura puede destruirla mientras se ejecuta
(comportamiento documentado de asyncio). Así se usaban la descarga de modelos,
el entrenamiento del laboratorio o la conexión de los conectores MCP: podían
detenerse sin error ni aviso, con la barra de progreso congelada.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("andromeda.background")

_tareas: set[asyncio.Task] = set()


def spawn(coro, *, name: str | None = None) -> asyncio.Task:
    """Lanza una corrutina en segundo plano conservando su referencia.

    Los errores se registran en vez de perderse ("Task exception was never
    retrieved").
    """
    tarea = asyncio.create_task(coro, name=name)
    _tareas.add(tarea)

    def _fin(t: asyncio.Task) -> None:
        _tareas.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.warning(f"Tarea en segundo plano {t.get_name()} falló: {t.exception()!r}")

    tarea.add_done_callback(_fin)
    return tarea


def pending() -> int:
    return len(_tareas)
