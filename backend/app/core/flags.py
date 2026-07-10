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
    "andromeda_artifacts_enabled":     True,   # panel de artefactos
    "andromeda_inline_viz":            True,   # visualizaciones integradas
    "andromeda_file_creation":         True,   # creación/edición de archivos
    "andromeda_network_egress":        False,  # salida de red (búsqueda web)
    "andromeda_model_fallback":        True,   # cambiar de modelo al fallar
    "andromeda_serve_production":      False,  # servir el modelo promovido a producción (registry)
}


def _state_path(settings) -> Path:
    base = Path(getattr(settings, "memory_db_path", "data/memory.db")).parent
    return base / "ui_state.json"


def _load(settings) -> dict:
    p = _state_path(settings)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


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


def all_flags(settings) -> dict[str, bool]:
    return {k: get_flag(settings, k) for k in _DEFAULTS}
