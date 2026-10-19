"""fsutil.py — Escritura segura de archivos pequeños de estado."""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    """Escribe en un temporal y lo renombra: nunca deja el archivo a medias.

    Si la app se cierra durante una escritura directa, el archivo queda
    truncado y al volver a abrir se pierde su contenido (preferencias, estado).
    El renombrado es atómico en el mismo sistema de archivos.
    """
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, destino)
