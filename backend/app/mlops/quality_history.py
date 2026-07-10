"""
quality_history.py — Serie temporal de calidad + detección de drift + SLO.

Las métricas instantáneas dicen cómo va AHORA; esto guarda cómo ha ido EN EL
TIEMPO para poder ver degradación (drift) y comprobar SLOs. Es lo que separa
"tengo un dashboard" de "vigilo la salud del servicio y sé cuándo empeora".

- snapshot(): toma una foto (éxito, latencias, satisfacción) limitada a una por
  cubo de tiempo (por defecto 5 min) para no inflar la serie.
- assess_slo(): compara la ventana reciente contra los umbrales SLO y contra una
  ventana base anterior → estado (ok/breach) y tendencia (mejora/estable/empeora).

Persiste en JSON (local-first), escritura atómica, thread-safe.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_MAX_POINTS = 500
_BUCKET_SECONDS = 300   # 1 snapshot cada 5 min como máximo

# Objetivos de nivel de servicio (SLO) por defecto. Ajustables por entorno.
DEFAULT_SLO = {
    "success_rate_min": 95.0,    # % de peticiones con éxito
    "p95_latency_max": 8000.0,   # ms
    "satisfaction_min": 70.0,    # % de 👍 sobre el total de votos
}


class QualityHistory:
    def __init__(self, path: str | Path, slo: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.slo = {**DEFAULT_SLO, **(slo or {})}

    def _read(self) -> dict:
        if not self.path.exists():
            return {"points": []}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            d.setdefault("points", [])
            return d
        except Exception:
            return {"points": []}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self, metrics: dict, satisfaction: float | None) -> bool:
        """Añade una foto si ha pasado el cubo de tiempo. Devuelve True si guardó.

        `metrics` es el dict de MetricsCollector.get_summary().
        Si no hay peticiones registradas, no guarda nada (evita ruido de ceros).
        """
        total = metrics.get("total_requests", 0)
        if not total:
            return False
        now = time.time()
        with _lock:
            data = self._read()
            pts = data["points"]
            if pts and (now - pts[-1]["t"]) < _BUCKET_SECONDS:
                return False   # mismo cubo de tiempo: no duplicar
            pts.append({
                "t": now,
                "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "requests": total,
                "success_rate": metrics.get("success_rate_pct"),
                "p50": metrics.get("p50_latency_ms"),
                "p95": metrics.get("p95_latency_ms"),
                "degradation_rate": metrics.get("degradation_rate_pct"),
                "satisfaction": satisfaction,
            })
            data["points"] = pts[-_MAX_POINTS:]
            self._write(data)
            return True

    def series(self) -> list[dict]:
        return self._read()["points"]

    def assess_slo(self) -> dict:
        """Estado SLO actual + tendencia (drift) comparando ventanas recientes."""
        pts = self._read()["points"]
        out: dict = {"slo": self.slo, "n_points": len(pts), "status": {}, "trend": {}}
        if not pts:
            return out

        recent = pts[-1]
        # Estado SLO con el punto más reciente.
        def _ok(val, thr, mode):
            if val is None:
                return None
            return (val >= thr) if mode == "min" else (val <= thr)

        out["status"] = {
            "success_rate": {"value": recent["success_rate"],
                             "ok": _ok(recent["success_rate"], self.slo["success_rate_min"], "min")},
            "p95_latency":  {"value": recent["p95"],
                             "ok": _ok(recent["p95"], self.slo["p95_latency_max"], "max")},
            "satisfaction": {"value": recent["satisfaction"],
                             "ok": _ok(recent["satisfaction"], self.slo["satisfaction_min"], "min")},
        }

        # Tendencia (drift): media de la última mitad vs la mitad anterior.
        out["trend"] = self._trend(pts)
        out["breaching"] = any(s["ok"] is False for s in out["status"].values())
        return out

    @staticmethod
    def _trend(pts: list[dict]) -> dict:
        """Compara la mitad reciente con la anterior para cada métrica."""
        if len(pts) < 4:
            return {}
        mid = len(pts) // 2
        prev, recent = pts[:mid], pts[mid:]

        def _avg(rows, key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        trend = {}
        for key, better in (("satisfaction", "up"), ("success_rate", "up"),
                            ("p95", "down"), ("p50", "down")):
            a, b = _avg(prev, key), _avg(recent, key)
            if a is None or b is None:
                continue
            delta = b - a
            # "degrading" si va en el sentido malo de forma apreciable (>3% relativo).
            rel = (delta / a * 100) if a else 0.0
            if abs(rel) < 3:
                direction = "stable"
            elif (delta > 0 and better == "up") or (delta < 0 and better == "down"):
                direction = "improving"
            else:
                direction = "degrading"
            trend[key] = {"from": round(a, 1), "to": round(b, 1),
                          "change_pct": round(rel, 1), "direction": direction}
        return trend
