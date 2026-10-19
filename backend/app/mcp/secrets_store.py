"""
secrets_store.py — Almacén local de claves de API para servidores MCP.

Hasta ahora las claves solo podían darse como variables de entorno antes de
arrancar la app, lo que en una aplicación de escritorio es inviable: el usuario
abre Andromeda con doble clic, no desde una terminal donde exportar variables.

Este módulo guarda las claves en un JSON dentro del directorio de datos del
usuario y las carga en `os.environ` al arrancar, de modo que todo el código
existente (que usa `os.path.expandvars` y `os.environ.get`) sigue funcionando
sin cambios.

Sobre la seguridad: el fichero se guarda con permisos 0600 (solo el usuario
propietario puede leerlo). No se cifra, y es importante ser honesto al
respecto: cifrarlo con una clave que la propia app debe poder leer no añade
seguridad real, solo la apariencia de ella. La protección efectiva aquí es la
del sistema de ficheros y el hecho de que todo es local.
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
from pathlib import Path

logger = logging.getLogger("andromeda.secrets")

_lock = threading.Lock()
_path: Path | None = None


def init(data_dir: str | Path) -> int:
    """Fija la ruta del almacén y carga las claves guardadas en os.environ.

    Devuelve el número de claves cargadas. Las variables ya presentes en el
    entorno tienen prioridad: si alguien arranca la app con una variable
    exportada, esa gana sobre la guardada.
    """
    global _path
    _path = Path(data_dir) / "mcp_secrets.json"
    loaded = 0
    for key, value in _read().items():
        if value and not os.environ.get(key):
            os.environ[key] = value
            loaded += 1
    if loaded:
        logger.info(f"  Claves MCP cargadas desde el almacén local: {loaded}")
    return loaded


def _read() -> dict[str, str]:
    if _path is None or not _path.exists():
        return {}
    try:
        data = json.loads(_path.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if isinstance(k, str)}
    except Exception as exc:
        logger.warning(f"No se pudo leer el almacén de claves: {exc}")
        return {}


def _write(data: dict[str, str]) -> None:
    if _path is None:
        raise RuntimeError("Almacén de claves no inicializado")
    _path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _path)
    try:
        # 0600: lectura/escritura solo para el propietario.
        _path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass   # algunos sistemas de ficheros (p. ej. FAT) no soportan chmod


def set_key(key: str, value: str) -> None:
    """Guarda una clave y la aplica al entorno del proceso en curso."""
    key = (key or "").strip()
    if not key:
        raise ValueError("Nombre de variable vacío")
    with _lock:
        data = _read()
        data[key] = value
        _write(data)
    os.environ[key] = value


def delete_key(key: str) -> bool:
    """Borra una clave del almacén y del entorno."""
    with _lock:
        data = _read()
        existed = data.pop(key, None) is not None
        if existed:
            _write(data)
    os.environ.pop(key, None)
    return existed


def has_key(key: str) -> bool:
    """True si la variable está disponible (guardada o exportada en el entorno)."""
    return bool(os.environ.get(key))


def status(keys: list[str]) -> dict[str, bool]:
    """Qué claves de la lista están configuradas. Nunca devuelve los valores."""
    return {k: has_key(k) for k in keys or []}


def list_configured() -> list[str]:
    """Nombres de las claves guardadas (sin sus valores, que no salen de aquí)."""
    return sorted(_read().keys())
