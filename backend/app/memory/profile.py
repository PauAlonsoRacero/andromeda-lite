"""
profile.py — Perfil de memoria unificado, estilo Claude.

A diferencia del store semántico (que guarda fragmentos de conversaciones para
poder buscarlas), el PERFIL es UN SOLO bloque de texto con lo que Andromeda sabe
del usuario de forma persistente: cómo se llama, en qué idioma quiere que le
hablen, con qué stack trabaja, sus preferencias.

Claves de diseño:
- Es texto cohesivo, no "declaraciones sueltas". La UI lo muestra como un único
  bloque editable, igual que la memoria de Claude.
- Los hechos automáticos van indexados por TOPIC (idioma, nombre, stack…). Al
  llegar uno nuevo del mismo topic, REEMPLAZA al anterior. Por eso "prefiero
  catalán" sustituye a "prefiero alemán" en vez de acumular ambos.
- El usuario puede editar el bloque entero a mano (campo `manual`). Lo que
  escribe manda y nunca se borra solo.

Persistencia: un JSON junto a la base de datos de memoria (sobrevive a reinicios
del .exe, donde localStorage no es fiable).
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

_lock = threading.Lock()

# Orden en que se renderizan los hechos para que el texto se lea natural.
_TOPIC_ORDER = ["nombre", "idioma", "stack", "rol", "ubicacion", "objetivo"]

# Detecta una frase de preferencia de idioma en texto libre, para poder limpiar
# un idioma viejo del bloque manual cuando llega uno nuevo desde el chat.
_LANG_LINE = re.compile(
    r"[^.\n]*\b(idioma|lengua|habl|respond|escrib)[^.\n]*"
    r"\b(español|castellano|catalán|catalan|inglés|ingles|alemán|aleman|"
    r"francés|frances|italiano|portugués|portugues|chino|japonés|japones)\b[^.\n]*\.?",
    re.IGNORECASE,
)


class MemoryProfile:
    """Perfil de memoria persistente del usuario (un único bloque de texto)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── E/S ──────────────────────────────────────────────────────────────────
    def _read(self) -> dict:
        if not self.path.exists():
            return {"facts": {}, "manual": "", "updated_at": None}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.setdefault("facts", {})
            data.setdefault("manual", "")
            data.setdefault("updated_at", None)
            return data
        except Exception:
            return {"facts": {}, "manual": "", "updated_at": None}

    def _write(self, data: dict) -> None:
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── Operaciones ────────────────────────────────────────────────────────────
    def upsert_fact(self, topic: str, sentence: str) -> None:
        """Inserta o REEMPLAZA el hecho de un topic. Garantiza no acumular
        contradicciones (idioma alemán → catalán reemplaza, no se suma)."""
        sentence = (sentence or "").strip()
        if not topic or not sentence:
            return
        with _lock:
            data = self._read()
            data["facts"][topic] = sentence
            # Si el topic es 'idioma', limpiar cualquier preferencia de idioma
            # antigua que viviera en el texto manual (caso: el usuario escribió
            # "prefiero alemán" a mano y luego dijo "catalán" en el chat).
            if topic == "idioma" and data.get("manual"):
                data["manual"] = _LANG_LINE.sub("", data["manual"]).strip()
            self._write(data)

    def delete_fact(self, topic: str) -> bool:
        with _lock:
            data = self._read()
            if topic in data["facts"]:
                del data["facts"][topic]
                self._write(data)
                return True
        return False

    def set_manual(self, text: str) -> None:
        """El usuario edita el bloque entero a mano. Su texto manda."""
        with _lock:
            data = self._read()
            data["manual"] = (text or "").strip()
            self._write(data)

    def clear(self) -> None:
        with _lock:
            self._write({"facts": {}, "manual": "", "updated_at": None})

    # ── Lectura / render ────────────────────────────────────────────────────────
    def get(self) -> dict:
        data = self._read()
        return {
            "manual": data["manual"],
            "facts": data["facts"],
            "text": self.render(data),
            "updated_at": data["updated_at"],
            "is_empty": not data["manual"] and not data["facts"],
        }

    def render(self, data: dict | None = None) -> str:
        """Devuelve el perfil como UN bloque de texto cohesivo (estilo Claude)."""
        data = data or self._read()
        parts: list[str] = []
        if data.get("manual"):
            parts.append(data["manual"].strip())
        facts = data.get("facts", {})
        # Orden estable: primero los topics conocidos, luego el resto.
        ordered = [t for t in _TOPIC_ORDER if t in facts]
        ordered += [t for t in facts if t not in _TOPIC_ORDER]
        for t in ordered:
            s = facts[t].strip()
            if s:
                parts.append(s if s.endswith((".", "!", "?")) else s + ".")
        return "\n".join(parts).strip()
