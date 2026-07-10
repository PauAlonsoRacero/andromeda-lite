"""
ab_testing.py — Framework de experimentos A/B para modelos.

Permite comparar dos (o más) modelos sirviendo a una fracción del tráfico cada
uno y midiendo qué variante rinde mejor (tasa de éxito, latencia). Es un patrón
central de MLOps: no decides "a ojo" qué modelo es mejor, lo mides en producción.

Diseño:
- Un experimento tiene variantes, cada una con un modelo y un peso de tráfico.
- La asignación es DETERMINISTA por una clave (p.ej. id de conversación): la
  misma conversación cae siempre en la misma variante (experiencia consistente),
  pero el reparto global respeta los pesos.
- Cada resultado (éxito + latencia) se acumula por variante.
- El estado se persiste en JSON (local-first, sin servidor extra).

No usa aleatoriedad no reproducible: el hash de la clave determina la variante.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()


class ABTesting:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── E/S ──────────────────────────────────────────────────────────────────
    def _read(self) -> dict:
        if not self.path.exists():
            return {"experiments": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"experiments": {}}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── Gestión de experimentos ────────────────────────────────────────────────
    def create(self, exp_id: str, variants: list[dict], active: bool = True) -> dict:
        """variants: [{"name": "A", "model": "mistral:7b", "weight": 50}, ...]

        También acepta strings ("mistral:7b") y los normaliza a variantes A/B/C…
        con pesos iguales, para que la API no falle con el payload más natural.
        """
        norm = []
        for i, v in enumerate(variants or []):
            if isinstance(v, str):
                norm.append({"name": chr(65 + i), "model": v,
                             "weight": max(1, 100 // max(1, len(variants)))})
            elif isinstance(v, dict) and v.get("model"):
                v.setdefault("name", chr(65 + i))
                norm.append(v)
        variants = norm
        with _lock:
            data = self._read()
            data["experiments"][exp_id] = {
                "id": exp_id,
                "active": active,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "variants": {
                    v["name"]: {
                        "model": v["model"],
                        "weight": int(v.get("weight", 50)),
                        "requests": 0, "successes": 0, "latency_sum_ms": 0.0,
                        # Señal de CALIDAD (feedback de usuario 👍/👎), no solo
                        # que la inferencia terminara: 'ratings' = votos totales,
                        # 'positive' = pulgares arriba.
                        "ratings": 0, "positive": 0,
                    } for v in variants
                },
            }
            self._write(data)
            return data["experiments"][exp_id]

    def list(self) -> list[dict]:
        return list(self._read()["experiments"].values())

    def get(self, exp_id: str) -> dict | None:
        return self._read()["experiments"].get(exp_id)

    def set_active(self, exp_id: str, active: bool) -> bool:
        with _lock:
            data = self._read()
            if exp_id in data["experiments"]:
                data["experiments"][exp_id]["active"] = active
                self._write(data)
                return True
        return False

    def delete(self, exp_id: str) -> bool:
        with _lock:
            data = self._read()
            if exp_id in data["experiments"]:
                del data["experiments"][exp_id]
                self._write(data)
                return True
        return False

    # ── Asignación y registro ───────────────────────────────────────────────────
    def active_experiment(self) -> dict | None:
        """Devuelve el primer experimento activo (Lite soporta uno a la vez)."""
        for exp in self._read()["experiments"].values():
            if exp.get("active"):
                return exp
        return None

    def assign(self, exp: dict, key: str) -> tuple[str, str]:
        """Asigna una variante de forma determinista por la clave. Respeta pesos.
        Devuelve (nombre_variante, modelo)."""
        variants = exp["variants"]
        total_w = sum(v["weight"] for v in variants.values()) or 1
        # hash estable de la clave → punto en [0, total_w)
        h = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % total_w
        acc = 0
        for name, v in variants.items():
            acc += v["weight"]
            if h < acc:
                return name, v["model"]
        name = next(iter(variants))
        return name, variants[name]["model"]

    def record(self, exp_id: str, variant: str, success: bool, latency_ms: float) -> None:
        with _lock:
            data = self._read()
            exp = data["experiments"].get(exp_id)
            if not exp or variant not in exp["variants"]:
                return
            v = exp["variants"][variant]
            v["requests"] += 1
            if success:
                v["successes"] += 1
            v["latency_sum_ms"] += max(0.0, float(latency_ms or 0))
            self._write(data)

    def record_quality(self, exp_id: str, variant: str, positive: bool) -> None:
        """Registra feedback de usuario (👍/👎) como señal de CALIDAD."""
        with _lock:
            data = self._read()
            exp = data["experiments"].get(exp_id)
            if not exp or variant not in exp["variants"]:
                return
            v = exp["variants"][variant]
            v.setdefault("ratings", 0)
            v.setdefault("positive", 0)
            v["ratings"] += 1
            if positive:
                v["positive"] += 1
            self._write(data)

    # ── Resultados ───────────────────────────────────────────────────────────────
    def results(self, exp_id: str) -> dict | None:
        exp = self.get(exp_id)
        if not exp:
            return None
        out = {"id": exp_id, "active": exp["active"], "variants": {}}
        for name, v in exp["variants"].items():
            req = v["requests"]
            sr = (v["successes"] / req * 100) if req else 0.0
            avg = (v["latency_sum_ms"] / req) if req else 0.0
            ratings = v.get("ratings", 0)
            positive = v.get("positive", 0)
            satisfaction = (positive / ratings * 100) if ratings else None
            out["variants"][name] = {
                "model": v["model"], "weight": v["weight"], "requests": req,
                "successes": v["successes"],
                "success_rate": round(sr, 1), "avg_latency_ms": round(avg, 1),
                # Calidad percibida por el usuario (👍/👎).
                "ratings": ratings, "positive": positive,
                "satisfaction": round(satisfaction, 1) if satisfaction is not None else None,
            }
        # Veredicto con rigor estadístico (test z + muestra mínima), no "a ojo".
        from app.mlops.stats import assess, assess_quality
        out.update(assess(exp["variants"]))
        out.update(assess_quality(exp["variants"]))
        return out

    def export_metrics(self) -> dict:
        """Para Prometheus: {exp_id: {variants: {variant: {requests, success_rate}}}}."""
        data = self._read()["experiments"]
        out = {}
        for exp_id, exp in data.items():
            out[exp_id] = {"variants": {}}
            for name, v in exp["variants"].items():
                req = v["requests"]
                out[exp_id]["variants"][name] = {
                    "requests": req,
                    "success_rate": (v["successes"] / req * 100) if req else 0.0,
                }
        return out
