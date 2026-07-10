"""
mlflow_client.py — Integración opcional con un servidor MLflow.

Patrón MLOps: cada inferencia es un "run" con parámetros (modelo, estrategia,
hardware) y métricas (latencia, ttft, éxito). Registrarlos en MLflow permite
comparar modelos a lo largo del tiempo, ver tendencias y versionar qué modelo se
usó para qué — trazabilidad real, no a ojo.

Es OPCIONAL y a prueba de fallos: si el paquete `mlflow` no está instalado o el
servidor no responde, el logger entra en modo no-op y la app sigue funcionando
igual (local-first no debe depender de un servidor externo). Se activa con
mlflow_enabled=true y un mlflow_tracking_uri válido.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("andromeda.mlflow")


class MLflowLogger:
    def __init__(self, tracking_uri: str, experiment: str = "andromeda"):
        self.enabled = False
        self._mlflow = None
        try:
            import mlflow  # import perezoso: solo si está instalado
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(experiment)
            self._mlflow = mlflow
            self.enabled = True
            logger.info(f"MLflow activo en {tracking_uri} (experimento '{experiment}')")
        except ImportError:
            logger.warning("MLflow activado en config pero el paquete 'mlflow' no está instalado.")
        except Exception as e:
            logger.warning(f"No se pudo conectar a MLflow ({tracking_uri}): {e}")

    def log_run(self, params: dict, metrics: dict, tags: dict | None = None) -> None:
        """Registra un run completo (params + métricas) de forma atómica."""
        if not self.enabled:
            return
        try:
            with self._mlflow.start_run():
                if params:
                    self._mlflow.log_params({k: v for k, v in params.items() if v is not None})
                if metrics:
                    clean = {k: float(v) for k, v in metrics.items()
                             if isinstance(v, (int, float))}
                    if clean:
                        self._mlflow.log_metrics(clean)
                if tags:
                    self._mlflow.set_tags(tags)
        except Exception as e:
            logger.debug(f"MLflow log_run falló (ignorado): {e}")
