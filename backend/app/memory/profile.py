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
import logging
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


logger = logging.getLogger("andromeda.memory.profile")


def _es_basura(frase: str) -> bool:
    """Un "hecho" que no aporta nada: "It please.", "Esto.", "Ok"."""
    import re as _re
    limpio = _re.sub(r"[\s\.,!¡¿?]+", " ", (frase or "")).strip().lower()
    # Sin regla de longitud: "Pau" o "Rust" son datos válidos y cortos. Solo se
    # descarta lo que es literalmente relleno.
    if not limpio:
        return True
    # Contradictorio: "Me gusta el color negro? lo odio." (guardado por una
    # versión anterior al pedir justo olvidarlo). Un gusto con un rechazo
    # explícito en la misma frase no es un gusto.
    if (_re.search(r"\b(me gusta|me encanta|i like|i love|j'aime|ich mag)\b", limpio)
            and _re.search(r"\b(lo odio|la odio|odio|detesto|no me gusta|i hate|hate it|"
                           r"don't like|je déteste|ich hasse)\b", limpio)):
        return True
    return bool(_re.fullmatch(
        r"(it|this|that|esto|eso|lo|please|por favor|porfavor|ok|vale)"
        r"( (please|por favor|porfavor|it|this))*", limpio))


class MemoryProfile:
    """Perfil de memoria persistente del usuario (un único bloque de texto)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:      # disco de solo lectura: _write lo tolera después
            logger.warning(f"No se pudo crear la carpeta del perfil: {exc}")

    # ── E/S ──────────────────────────────────────────────────────────────────
    def _read(self) -> dict:
        if not self.path.exists():
            return {"facts": {}, "manual": "", "updated_at": None}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.setdefault("facts", {})
            data.setdefault("manual", "")
            data.setdefault("updated_at", None)
            # Limpieza de hechos basura guardados por versiones anteriores del
            # extractor (p. ej. "It please." de "remember it please"). El
            # extractor ya no los genera, pero los antiguos seguían guardados y
            # se inyectaban en CADA mensaje.
            basura = [k for k, v in data["facts"].items() if _es_basura(v)]
            if basura:
                for k in basura:
                    data["facts"].pop(k, None)
                try:
                    self._write(data)
                except Exception:                         # noqa: BLE001
                    pass
            return data
        except Exception:
            return {"facts": {}, "manual": "", "updated_at": None}

    def _write(self, data: dict) -> None:
        """Persiste el perfil. Un fallo de disco no puede romper el chat.

        Si el disco está lleno o falta permiso, se registra y se continúa en vez
        de propagar la excepción hasta la petición del usuario.
        """
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning(f"No se pudo guardar el perfil de memoria: {exc}")

    # ── Operaciones ────────────────────────────────────────────────────────────
    def upsert_fact(self, topic: str, sentence: str) -> None:
        """Inserta o REEMPLAZA el hecho de un topic. Garantiza no acumular
        contradicciones (idioma alemán → catalán reemplaza, no se suma)."""
        sentence = (sentence or "").strip()
        if not topic or not sentence or _es_basura(sentence):
            return
        with _lock:
            data = self._read()
            data["facts"][topic] = sentence
            # Fecha por dato: la vista de memoria muestra "Última actualización".
            import time as _t
            data.setdefault("meta", {})[topic] = _t.time()
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
                data.get("meta", {}).pop(topic, None)
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

    def clear_facts(self) -> int:
        """Borra lo aprendido de las conversaciones. Devuelve cuántos datos.

        Las notas escritas a mano en Ajustes se conservan: son configuración
        deliberada del usuario, no algo que la IA haya ido recogiendo.
        """
        with _lock:
            data = self._read()
            n = len(data.get("facts", {}))
            data["facts"] = {}
            data["meta"] = {}
            self._write(data)
        return n

    def forget_matching(self, texto: str) -> list[str]:
        """Olvida los datos que mencionan lo indicado ("olvida que me gusta el azul").

        Coincide por palabras con significado, para que "el azul" encuentre
        "Me gusta el color azul". Devuelve las frases eliminadas.
        """
        import re as _re
        claves = {w for w in _re.findall(r"[a-záéíóúñüàèç\u4e00-\u9fff]{3,}", (texto or "").lower())
                  if w not in {"que", "the", "that", "los", "las", "del", "por", "para",
                               "gusta", "like", "memoria", "memory", "olvida", "forget"}}
        if not claves:
            return []
        eliminadas = []
        with _lock:
            data = self._read()
            for k, frase in list(data.get("facts", {}).items()):
                if claves & set(_re.findall(r"[a-záéíóúñüàèç\u4e00-\u9fff]{3,}", frase.lower())):
                    eliminadas.append(frase)
                    data["facts"].pop(k)
            if eliminadas:
                self._write(data)
        return eliminadas

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
