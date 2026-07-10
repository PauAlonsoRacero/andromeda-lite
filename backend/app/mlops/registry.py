"""
registry.py — Model Registry con flujo de promoción (staging → production).

Esta es la pieza que convierte a Andromeda en un proyecto MLOps de ciclo
completo para un producto de inferencia: no basta con tener modelos en Ollama,
hay que VERSIONARLOS, evaluarlos, PROMOVER el mejor a producción y que el sistema
SIRVA exactamente esa versión promovida. Es el equivalente al Model Registry de
MLflow/SageMaker, pero local-first.

Ciclo: registrar versión (con su score de evaluación) → staging → production.
Solo hay UN modelo en "production" a la vez; promover otro archiva el anterior.

Estados: none · staging · production · archived
Persiste en JSON (local-first), con escritura atómica y thread-safe.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

_lock = threading.Lock()

STAGES = ("none", "staging", "production", "archived")


class ModelRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── Persistencia ─────────────────────────────────────────────────────────
    def _read(self) -> dict:
        if not self.path.exists():
            return {"versions": {}}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            d.setdefault("versions", {})
            return d
        except Exception:
            return {"versions": {}}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── Operaciones ──────────────────────────────────────────────────────────
    def register(self, model: str, version: str = "", eval_score: float | None = None,
                 notes: str = "") -> dict:
        """Registra una nueva versión de un modelo (estado inicial: staging)."""
        with _lock:
            data = self._read()
            vid = uuid.uuid4().hex[:12]
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            entry = {
                "id": vid,
                "model": model.strip(),
                "version": (version or "").strip() or _auto_version(data, model),
                "stage": "staging",
                "eval_score": eval_score,
                "notes": (notes or "")[:500],
                "created_at": now,
                "promoted_at": None,
            }
            data["versions"][vid] = entry
            self._write(data)
            return entry

    def list(self) -> list[dict]:
        data = self._read()
        return sorted(data["versions"].values(),
                      key=lambda e: e["created_at"], reverse=True)

    def get(self, vid: str) -> dict | None:
        return self._read()["versions"].get(vid)

    def promote(self, vid: str, stage: str) -> dict | None:
        """Cambia el estado de una versión. Promover a 'production' archiva
        automáticamente la versión que estuviera en producción (solo una a la vez).
        """
        if stage not in STAGES:
            raise ValueError(f"Estado inválido: {stage}")
        with _lock:
            data = self._read()
            entry = data["versions"].get(vid)
            if not entry:
                return None
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if stage == "production":
                # Archivar la producción actual (si la hay y es otra).
                for other in data["versions"].values():
                    if other["id"] != vid and other["stage"] == "production":
                        other["stage"] = "archived"
                entry["promoted_at"] = now
            entry["stage"] = stage
            self._write(data)
            return entry

    def delete(self, vid: str) -> bool:
        with _lock:
            data = self._read()
            if vid in data["versions"]:
                del data["versions"][vid]
                self._write(data)
                return True
            return False

    def production_model(self) -> str | None:
        """Devuelve el TAG del modelo actualmente en producción, o None."""
        for e in self._read()["versions"].values():
            if e["stage"] == "production":
                return e["model"]
        return None

    def production_entry(self) -> dict | None:
        for e in self._read()["versions"].values():
            if e["stage"] == "production":
                return e
        return None


def _auto_version(data: dict, model: str) -> str:
    """Genera una etiqueta de versión incremental v1, v2… por modelo."""
    n = sum(1 for e in data["versions"].values() if e["model"] == model.strip())
    return f"v{n + 1}"
