"""tracker.py — STUB Lite.

El dashboard MLOps (métricas, drift, percentiles, comparación de modelos) es
exclusivo de Andromeda Pro. En Lite el tracker mantiene la MISMA interfaz para
no romper el flujo de chat, pero solo hace un registro mínimo en memoria y las
consultas analíticas devuelven vacío. El router /api/mlops está desactivado en
Lite (ver app/__init__.py).
"""
from __future__ import annotations
import logging
import time
import uuid

logger = logging.getLogger("andromeda.mlops.lite")


class MLOpsTracker:
    """Stub de Lite: interfaz completa, sin analítica avanzada."""

    def __init__(self, db_path: str = "data/mlops_runs.db", mlflow_uri: str | None = None):
        self.db_path = db_path
        self._mlflow = None
        self._runs: dict[str, dict] = {}
        # Logger MLflow opcional: solo si se pasó una URI (mlflow_enabled=true).
        if mlflow_uri:
            try:
                from app.mlops.mlflow_client import MLflowLogger
                self._mlflow = MLflowLogger(mlflow_uri)
            except Exception:
                self._mlflow = None

    # — Ciclo de vida de un run (usado por el flujo de chat) —
    def start_run(self, *args, **kwargs) -> str:
        run_id = str(uuid.uuid4())
        self._runs[run_id] = {"start": time.time()}
        return run_id

    def log_metrics(self, run_id: str, metrics: dict) -> None:
        if run_id in self._runs:
            self._runs[run_id].update(metrics or {})

    def log_specialists(self, run_id: str, specialists, latencies=None) -> None:
        pass

    def log_degradation(self, run_id: str, reason: str, from_strategy: str, to_strategy: str) -> None:
        pass

    def end_run(self, run_id: str, success: bool = True) -> None:
        run = self._runs.pop(run_id, None)
        # Volcar el run a MLflow si está activo (params + métricas acumuladas).
        if run and self._mlflow and getattr(self._mlflow, "enabled", False):
            params = {k: run.get(k) for k in ("model", "strategy", "hardware_tier")}
            metrics = {k: run[k] for k in ("latency_ms", "ttft_ms") if k in run}
            metrics["success"] = 1.0 if success else 0.0
            self._mlflow.log_run(params, metrics, tags={"run_id": run_id})

    def update_model_registry(self, *args, **kwargs) -> None:
        pass

    # — Consultas analíticas: exclusivas de Pro → vacías en Lite —
    def get_experiment_summary(self, limit: int = 100) -> dict:
        return {"runs": [], "total": 0, "pro_only": True}

    def get_model_comparison(self, specialist_id: str) -> list:
        return []

    def get_all_models_used(self) -> list:
        return []

    def get_latency_percentiles(self) -> dict:
        return {}

    def get_timeseries(self, metric: str = "latency_ms", buckets: int = 20) -> list:
        return []

    def detect_drift(self, metric: str = "latency_ms", threshold_pct: float = 25.0) -> dict:
        return {"drift": False, "pro_only": True}

    def get_error_breakdown(self) -> dict:
        return {}

    def get_throughput(self) -> dict:
        return {}

    def export_csv(self) -> str:
        return "metric,value\n"

    def export_prometheus(self) -> str:
        return "# MLOps export disponible solo en Andromeda Pro\n"
