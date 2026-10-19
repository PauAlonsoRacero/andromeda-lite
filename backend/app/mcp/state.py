"""
state.py — Qué conectores MCP tiene activados el usuario.

Antes el estado se escribía dentro del mcp_servers.yaml de la propia app. En
Windows ese archivo está en C:\\Program Files y no se puede escribir sin permisos
de administrador: activar un conector fallaba. Además, cada actualización de la
app reemplazaba el YAML y el usuario perdía sus conectores.

Ahora el catálogo (el YAML) es de solo lectura y el estado vive en la carpeta de
datos del usuario, aplicado encima.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _path() -> Path:
    base = os.environ.get("ANDROMEDA_DATA_DIR") or str(
        Path(os.environ.get("ANDROMEDA_MEMORY_DB_PATH", "data/memory.db")).parent)
    return Path(base) / "mcp_state.json"


def overrides() -> dict[str, bool]:
    try:
        datos = json.loads(_path().read_text(encoding="utf-8"))
        return {str(k): bool(v) for k, v in (datos.get("enabled") or {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def set_enabled(server_id: str, enabled: bool) -> None:
    from app.core.fsutil import atomic_write_text
    actual = overrides()
    actual[server_id] = bool(enabled)
    atomic_write_text(_path(), json.dumps({"enabled": actual}, indent=2))


def apply(config: dict) -> dict:
    """Aplica el estado del usuario sobre el catálogo (en memoria)."""
    servidores = (config or {}).get("servers") or {}
    for sid, en in overrides().items():
        if sid in servidores:
            servidores[sid]["enabled"] = en
    return config
