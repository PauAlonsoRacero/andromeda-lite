"""
flags.py — Lectura de los toggles de configuración (Memoria, Visuales,
Ejecución de archivos, Red…) que el usuario activa/desactiva en Ajustes.

El frontend los guarda en ui_state.json vía /api/uistate (misma fuente que el
resto de ajustes). Aquí los leemos en el backend para GATEAR comportamiento real:
si "Generar memoria" está off, no extraemos; si "Permitir salida de red" está
off, no buscamos en la web; etc.

Cada flag tiene un valor por defecto sensato para que, si el archivo aún no
existe, el comportamiento sea el esperado.
"""
from __future__ import annotations

import json
from pathlib import Path

# Defaults: clave de uistate → valor por defecto.
_DEFAULTS: dict[str, bool] = {
    "andromeda_mem_autogenerate":      True,   # generar memoria del historial
    "andromeda_mem_conversation_search": True, # buscar y referenciar conversaciones
    # Guardar en memoria temas sensibles (salud, religión, política…). Activado por
    # defecto porque Pau pidió explícitamente que se recuerden objetivos como
    # "quiero bajar de peso"; al apagarlo se eliminan los ya guardados.
    "andromeda_mem_sensitive":          True,
    "andromeda_artifacts_enabled":     True,   # panel de artefactos
    "andromeda_inline_viz":            True,   # visualizaciones integradas
    "andromeda_file_creation":         True,   # creación/edición de archivos
    "andromeda_network_egress":        True,   # búsqueda web: activa por defecto;
                                              # el modo incógnito la desactiva
                                              # aparte, sin tocar este flag
    "andromeda_model_fallback":        True,   # cambiar de modelo al fallar
    "andromeda_serve_production":      False,  # servir el modelo promovido a producción (registry)
}


def _state_path(settings) -> Path:
    base = Path(getattr(settings, "memory_db_path", "data/memory.db")).parent
    return base / "ui_state.json"


_cache: dict = {}   # ruta → (mtime, datos)


def _load(settings) -> dict:
    """Estado de las capacidades. Se consulta varias veces por mensaje: se
    cachea y solo se vuelve a leer si el archivo cambió (por fecha de
    modificación), así que un cambio en Ajustes se ve al instante."""
    p = _state_path(settings)
    try:
        st = p.stat()
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    guardado = _cache.get(str(p))
    if guardado and guardado[0] == mtime:
        return dict(guardado[1])
    try:
        datos = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    _cache[str(p)] = (mtime, datos)
    return dict(datos)


def get_flag(settings, key: str) -> bool:
    """Devuelve el valor booleano de un flag, con su default si no está fijado."""
    data = _load(settings)
    if key in data:
        v = data[key]
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)
    return _DEFAULTS.get(key, False)

