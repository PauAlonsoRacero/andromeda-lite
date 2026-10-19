"""
output_filters.py — Limpieza del texto que genera el modelo, en streaming.

El prompt del sistema incluye la fecha y la hora actuales para que el modelo no
use la de su entrenamiento. Algunos modelos (gemma3 en los registros de Pau) la
recitaban al principio de CADA respuesta —"Hoy es viernes, 25 de septiembre de
2026, y son las 22:36."— y en las respuestas con herramientas, en cada ronda.

El filtro elimina una línea que sea solo esa frase. Solo retiene las líneas que
EMPIEZAN como una fecha; el resto pasa sin espera.
"""
from __future__ import annotations

import re

# Comienzos posibles de la frase de fecha, en los cinco idiomas.
_INICIO = re.compile(r"^\s*(hoy\s+es|hoy,|today\s+is|it\s+is\s+(now\s+)?\w+day|heute\s+ist|"
                     r"nous\s+sommes|aujourd['’]hui|今天是)", re.IGNORECASE)
# La línea completa: comienzo de fecha + (día/mes/año u hora) + fin, sin más contenido.
_LINEA_FECHA = re.compile(
    r"^\s*(hoy\s+es|hoy,|today\s+is|it\s+is\s+(now\s+)?\w+day|heute\s+ist|nous\s+sommes|"
    r"aujourd['’]hui|今天是)[^\n]{0,140}?(\d{4}|\d{1,2}[:h.]\d{2})[^\n]{0,40}$",
    re.IGNORECASE)
_MAX_RETENIDO = 200


class DateEchoFilter:
    """Filtro con estado: feed(trozo) → texto a emitir; flush() al terminar."""

    def __init__(self) -> None:
        self._linea = ""          # línea en curso retenida
        self._decidido = False    # ya se sabe que esta línea no es una fecha
        self._saltar_vacia = False

    def _cerrar_linea(self, linea: str) -> str:
        return "" if _LINEA_FECHA.match(linea.rstrip()) else linea

    def feed(self, trozo: str) -> str:
        salida = []
        for ch in trozo:
            if self._decidido:
                salida.append(ch)
                if ch == "\n":
                    self._decidido = False
                continue
            self._linea += ch
            if ch == "\n":
                linea = self._linea[:-1]
                if not linea.strip():
                    if not self._saltar_vacia:
                        salida.append(self._linea)      # línea vacía: salto de párrafo
                    self._saltar_vacia = False
                elif _LINEA_FECHA.match(linea.rstrip()):
                    # Se elimina la frase y la línea en blanco que suele seguirla.
                    self._saltar_vacia = True
                else:
                    salida.append(self._linea)
                self._linea = ""
                continue
            self._saltar_vacia = False
            prefijo = self._linea.lstrip()
            if len(prefijo) >= 14 and not _INICIO.match(self._linea):
                salida.append(self._linea)
                self._linea, self._decidido = "", True
            elif len(self._linea) > _MAX_RETENIDO:
                salida.append(self._linea)
                self._linea, self._decidido = "", True
        return "".join(salida)

    def flush(self) -> str:
        resto = self._cerrar_linea(self._linea) if self._linea else ""
        self._linea = ""
        return resto


def strip_date_echo(texto: str) -> str:
    """Versión para respuestas completas (camino sin streaming)."""
    f = DateEchoFilter()
    return f.feed(texto) + f.flush()
