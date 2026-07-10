"""
feedback.py — Almacén de feedback de usuario (👍/👎) sobre las respuestas.

Es la señal de CALIDAD online: ¿la respuesta le sirvió al usuario? A diferencia
de "éxito" (la inferencia terminó) o "latencia" (fue rápida), esto mide si la
respuesta fue BUENA. Alimenta el A/B (qué modelo satisface más) y da una métrica
de satisfacción global.

Persiste agregados en JSON (local-first). Guarda también los últimos votos para
poder inspeccionarlos.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_MAX_RECENT = 200


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"up": 0, "down": 0, "recent": []}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            d.setdefault("up", 0); d.setdefault("down", 0); d.setdefault("recent", [])
            return d
        except Exception:
            return {"up": 0, "down": 0, "recent": []}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, request_id: str, positive: bool, model: str | None = None,
               comment: str | None = None) -> None:
        with _lock:
            data = self._read()
            if positive:
                data["up"] += 1
            else:
                data["down"] += 1
            data["recent"].insert(0, {
                "request_id": request_id,
                "positive": positive,
                "model": model,
                "comment": (comment or "")[:280],
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            data["recent"] = data["recent"][:_MAX_RECENT]
            self._write(data)

    def stats(self) -> dict:
        data = self._read()
        total = data["up"] + data["down"]
        return {
            "up": data["up"],
            "down": data["down"],
            "total": total,
            "satisfaction": round(data["up"] / total * 100, 1) if total else None,
            "recent": data["recent"][:20],
        }
