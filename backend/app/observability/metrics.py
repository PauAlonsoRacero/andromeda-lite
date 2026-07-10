"""
metrics.py — Colector de métricas en memoria de Andromeda.

Mantiene una ventana deslizante de las últimas N peticiones para
calcular métricas operativas sin consultar SQLite.

Más rápido que SQLite para métricas en tiempo real.
Se pierde al reiniciar (los datos persistentes están en TraceStore).
"""

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("andromeda.metrics")

# Máximo de entradas en la ventana deslizante
MAX_WINDOW = 1000


class MetricsCollector:
    """
    Colector de métricas en memoria con ventana deslizante.

    Mantiene las últimas MAX_WINDOW peticiones y calcula:
    - Latencias (avg, p50, p95, p99)
    - Success rate
    - Distribución de estrategias y especialistas
    - Tasa de degradación
    """

    def __init__(self) -> None:
        # Deque con tamaño máximo — automáticamente elimina los más antiguos
        self._window: deque[dict] = deque(maxlen=MAX_WINDOW)
        # Ventana separada para llamadas a herramientas MCP
        self._tool_window: deque[dict] = deque(maxlen=MAX_WINDOW)

    def record_tool_call(self, name: str, latency_ms: float, success: bool,
                         params: dict | None = None, error: str | None = None) -> None:
        """Registra la ejecución de una herramienta MCP (analytics).

        Los parámetros se sanitizan: solo se guardan las CLAVES y el tamaño del
        valor, nunca el contenido (puede tener datos sensibles o ser enorme).
        """
        safe_params = {}
        if params:
            for k, v in params.items():
                safe_params[k] = f"<{type(v).__name__}:{len(str(v))} chars>"
        self._tool_window.append({
            "tool": name,
            "latency_ms": round(latency_ms, 1),
            "success": success,
            "params": safe_params,
            "error": (error or "")[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_tool_summary(self) -> dict:
        """Resumen de uso de herramientas MCP: conteo, latencia, error rate."""
        entries = list(self._tool_window)
        if not entries:
            return {"total_calls": 0, "by_tool": {}}
        by_tool: dict[str, dict] = {}
        for e in entries:
            t = by_tool.setdefault(e["tool"], {"calls": 0, "errors": 0, "latencies": []})
            t["calls"] += 1
            if not e["success"]:
                t["errors"] += 1
            if e["latency_ms"] > 0:
                t["latencies"].append(e["latency_ms"])
        for t, d in by_tool.items():
            lat = d.pop("latencies")
            d["avg_latency_ms"] = round(sum(lat) / len(lat), 1) if lat else 0
            d["error_rate"] = round(d["errors"] / d["calls"], 3) if d["calls"] else 0
        return {
            "total_calls": len(entries),
            "by_tool": by_tool,
            "recent": entries[-10:],
        }

    def record(self, request_id: str, data: dict) -> None:
        """
        Registra una petición completada en la ventana.

        Args:
            request_id: UUID del request
            data: Métricas de la petición:
                  {latency_ms, ttft_ms, success, strategy, specialists_used,
                   hardware_tier, degraded, timestamp}
        """
        entry = {
            "request_id": request_id,
            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "latency_ms": data.get("latency_ms", 0.0),
            "ttft_ms": data.get("ttft_ms", 0.0),
            "success": data.get("success", True),
            "strategy": data.get("strategy", "single"),
            "specialists_used": data.get("specialists_used", []),
            "hardware_tier": data.get("hardware_tier", 1),
            "degraded": data.get("degraded", False),
        }
        self._window.append(entry)

    def get_summary(self) -> dict:
        """
        Calcula y retorna el resumen de métricas de la ventana actual.

        Returns:
            Dict con todas las métricas calculadas
        """
        if not self._window:
            return {
                "total_requests": 0,
                "message": "Sin peticiones registradas aún",
            }

        entries = list(self._window)
        total = len(entries)

        # ── Latencias ─────────────────────────────────────────────────────
        latencies = sorted([e["latency_ms"] for e in entries if e["latency_ms"] > 0])
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

        ttft_list = [e["ttft_ms"] for e in entries if e["ttft_ms"] > 0]
        avg_ttft = sum(ttft_list) / len(ttft_list) if ttft_list else 0

        # ── Success rate ───────────────────────────────────────────────────
        successful = sum(1 for e in entries if e["success"])
        success_rate = successful / total * 100

        # ── Degradación ────────────────────────────────────────────────────
        degraded = sum(1 for e in entries if e["degraded"])
        degradation_rate = degraded / total * 100

        # ── Distribución de estrategias ────────────────────────────────────
        strategy_dist: dict[str, int] = {}
        for e in entries:
            s = e.get("strategy", "unknown")
            strategy_dist[s] = strategy_dist.get(s, 0) + 1

        most_used_strategy = max(strategy_dist, key=strategy_dist.get) if strategy_dist else "N/A"

        # ── Distribución de especialistas ──────────────────────────────────
        specialist_dist: dict[str, int] = {}
        for e in entries:
            for spec in e.get("specialists_used", []):
                specialist_dist[spec] = specialist_dist.get(spec, 0) + 1

        most_used_specialist = max(specialist_dist, key=specialist_dist.get) if specialist_dist else "N/A"

        # ── Peticiones en la última hora ───────────────────────────────────
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        requests_last_hour = sum(
            1 for e in entries
            if e.get("timestamp", "") >= one_hour_ago
        )

        # ── Promedio de especialistas por request ──────────────────────────
        avg_specialists = (
            sum(len(e.get("specialists_used", [])) for e in entries) / total
        )

        return {
            "window_size": total,
            "total_requests": total,
            "requests_last_hour": requests_last_hour,
            "success_rate_pct": round(success_rate, 1),
            "degradation_rate_pct": round(degradation_rate, 1),
            "avg_latency_ms": round(avg_latency, 0),
            "p50_latency_ms": round(p50, 0),
            "p95_latency_ms": round(p95, 0),
            "p99_latency_ms": round(p99, 0),
            "avg_ttft_ms": round(avg_ttft, 0),
            "avg_specialists_per_request": round(avg_specialists, 2),
            "most_used_strategy": most_used_strategy,
            "most_used_specialist": most_used_specialist,
            "strategy_distribution": strategy_dist,
            "specialist_distribution": specialist_dist,
        }
