"""
training_corpus.py — Datos de entrenamiento para Apolo.

La idea de Apolo es entrenar un modelo con el propio uso de Andromeda y dejar
que el pipeline A/B decida si mejora al modelo base. Pero la telemetría que ya
existía no servía para eso: las trazas guardan solo 100 caracteres del prompt,
ninguna respuesta, y rotan a 200 registros; los votos 👍/👎 guardan el id de la
petición, no el texto. Se tenía la señal y se tiraba el contenido.

Este módulo guarda pares completos (mensaje del usuario, respuesta del modelo)
y les asocia la valoración cuando llega. Después se exportan en el formato que
espera `mlx_lm.lora`.

PRIVACIDAD — decisiones deliberadas:
  • Desactivado por defecto: guardar conversaciones completas en disco solo
    debe ocurrir si el usuario lo pide.
  • Nunca en modo incógnito, esté activado o no.
  • Solo local: no hay ninguna vía de envío, únicamente exportar a un archivo.
  • Se puede vaciar entero desde la interfaz.
"""
from __future__ import annotations

import json
import logging
import random
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger("andromeda.training")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:
        @staticmethod
        def log(*a, **k): pass
    diag = _Nulo()

# Por debajo de esto una respuesta no enseña nada ("ok", "claro", errores).
_MIN_RESPONSE_CHARS = 40
# Por encima, casi siempre es un volcado (un archivo pegado entero) que distorsiona
# el entrenamiento más de lo que aporta.
_MAX_CHARS = 24_000


class TrainingCorpus:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "training_corpus.db"
        self.state_path = self.dir / "training_state.json"
        self._lock = threading.Lock()
        self._init_db()

    # ── Estado (activado / desactivado) ─────────────────────────────────────
    def is_enabled(self) -> bool:
        try:
            return bool(json.loads(self.state_path.read_text(encoding="utf-8")).get("enabled", False))
        except Exception:
            return False

    def set_enabled(self, value: bool) -> None:
        try:
            from app.core.fsutil import atomic_write_text
            atomic_write_text(self.state_path, json.dumps({"enabled": bool(value)}))
        except OSError as exc:
            logger.warning(f"No se pudo guardar el estado del corpus: {exc}")

    # ── Almacenamiento ──────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_db(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS samples (
                    request_id TEXT PRIMARY KEY,
                    ts         REAL NOT NULL,
                    model      TEXT DEFAULT '',
                    prompt     TEXT NOT NULL,
                    response   TEXT NOT NULL,
                    history    TEXT DEFAULT '[]',
                    rating     INTEGER            -- 1 bueno, -1 malo, NULL sin votar
                )
            """)

    def record(self, request_id: str, prompt: str, response: str, *,
               model: str = "", history: list | None = None,
               incognito: bool = False) -> bool:
        """Guarda un par. Devuelve True si se guardó."""
        if incognito or not self.is_enabled() or not request_id:
            return False
        prompt, response = (prompt or "").strip(), (response or "").strip()
        if len(response) < _MIN_RESPONSE_CHARS or not prompt:
            diag.log("training", "muestra descartada por corta",
                     data={"chars_respuesta": len(response)})
            return False
        if len(prompt) + len(response) > _MAX_CHARS:
            diag.log("training", "muestra descartada por larga",
                     data={"chars": len(prompt) + len(response)})
            return False
        # Solo los últimos turnos: el historial completo no cabe en un ejemplo.
        hist = [{"role": m.get("role"), "content": (m.get("content") or "")[:2000]}
                for m in (history or [])[-6:] if m.get("role") in ("user", "assistant")]
        try:
            with self._lock, self._conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO samples "
                    "(request_id, ts, model, prompt, response, history, rating) "
                    "VALUES (?, ?, ?, ?, ?, ?, "
                    "  (SELECT rating FROM samples WHERE request_id = ?))",
                    (request_id, time.time(), model or "", prompt, response,
                     json.dumps(hist, ensure_ascii=False), request_id))
            diag.log("training", "muestra guardada",
                     data={"modelo": model, "chars": len(prompt) + len(response)},
                     level="success")
            return True
        except sqlite3.Error as exc:
            logger.warning(f"No se pudo guardar la muestra: {exc}")
            return False

    def rate(self, request_id: str, positive: bool) -> None:
        """Asocia el voto 👍/👎 a una muestra ya guardada."""
        if not request_id:
            return
        try:
            with self._lock, self._conn() as c:
                c.execute("UPDATE samples SET rating = ? WHERE request_id = ?",
                          (1 if positive else -1, request_id))
        except sqlite3.Error as exc:
            logger.warning(f"No se pudo guardar la valoración: {exc}")

    def stats(self) -> dict:
        try:
            with self._lock, self._conn() as c:
                total, buenos, malos = c.execute(
                    "SELECT COUNT(*), "
                    "SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END), "
                    "SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) FROM samples"
                ).fetchone()
                modelos = dict(c.execute(
                    "SELECT model, COUNT(*) FROM samples GROUP BY model").fetchall())
        except sqlite3.Error:
            total, buenos, malos, modelos = 0, 0, 0, {}
        total, buenos, malos = total or 0, buenos or 0, malos or 0
        return {
            "enabled": self.is_enabled(),
            "total": total,
            "positive": buenos,
            "negative": malos,
            "unrated": total - buenos - malos,
            "by_model": modelos,
            # Referencia práctica: con LoRA se empieza a notar con unos cientos
            # de ejemplos buenos; por debajo el adaptador tiende a memorizar.
            "ready_for_training": buenos >= 200,
        }

    def clear(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM samples")

    # ── Exportación ─────────────────────────────────────────────────────────
    def export_mlx(self, out_dir: str | Path, *, include_unrated: bool = False,
                   valid_ratio: float = 0.1, seed: int = 42) -> dict:
        """Escribe train.jsonl y valid.jsonl en el formato chat de mlx_lm.

        Nunca exporta respuestas votadas como malas: entrenar con ellas enseña
        justo lo que el usuario ya dijo que no quiere. Las no votadas solo si se
        pide expresamente, porque su calidad es desconocida.

        El conjunto de validación es imprescindible: es lo que permite ver
        cuándo el adaptador empieza a memorizar (la pérdida de entrenamiento
        baja pero la de validación sube).
        """
        cond = "rating = 1" if not include_unrated else "(rating = 1 OR rating IS NULL)"
        with self._lock, self._conn() as c:
            filas = c.execute(
                # cond es uno de dos literales fijos de arriba, nunca entrada del usuario.
                f"SELECT prompt, response, history FROM samples WHERE {cond} "  # nosec B608
                "ORDER BY ts").fetchall()

        ejemplos = []
        for prompt, response, history in filas:
            try:
                hist = json.loads(history or "[]")
            except ValueError:
                hist = []
            ejemplos.append({"messages": hist + [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]})

        random.Random(seed).shuffle(ejemplos)
        n_valid = max(1, int(len(ejemplos) * valid_ratio)) if len(ejemplos) >= 10 else 0
        valid, train = ejemplos[:n_valid], ejemplos[n_valid:]

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for nombre, datos in (("train.jsonl", train), ("valid.jsonl", valid)):
            with (out / nombre).open("w", encoding="utf-8") as f:
                for e in datos:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")

        diag.log("training", f"exportado: {len(train)} train / {len(valid)} valid",
                 data={"carpeta": str(out)}, level="success")
        return {"train": len(train), "valid": len(valid), "path": str(out)}
