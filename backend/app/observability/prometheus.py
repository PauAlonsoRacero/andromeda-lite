"""
prometheus.py — Exposición de métricas en formato de texto Prometheus.

Genera la salida de /metrics SIN dependencias externas (no requiere el paquete
prometheus_client): el formato de exposición de texto de Prometheus es estable y
trivial de emitir, y así no añadimos peso al binario local-first.

Convierte lo que ya recoge MetricsCollector (latencias, éxito, herramientas) a
métricas con el nombre y tipo que Prometheus espera. Un servidor Prometheus las
scrapea periódicamente y Grafana las pinta.
"""
from __future__ import annotations


def _line(name: str, value, labels: dict | None = None) -> str:
    if labels:
        lbl = ",".join(f'{k}="{_escape(str(v))}"' for k, v in labels.items())
        return f"{name}{{{lbl}}} {value}"
    return f"{name} {value}"


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_metrics(summary: dict, tools: dict, ab: dict | None = None, version: str = "") -> str:
    """Construye el cuerpo de /metrics en formato Prometheus."""
    out: list[str] = []

    # Señal de vida + info de build (patrón estándar para alertas de "target down").
    out.append("# HELP andromeda_up El backend está vivo (siempre 1 si responde).")
    out.append("# TYPE andromeda_up gauge")
    out.append(_line("andromeda_up", 1))
    if version:
        out.append("# HELP andromeda_build_info Versión de Andromeda.")
        out.append("# TYPE andromeda_build_info gauge")
        out.append(_line("andromeda_build_info", 1, {"version": version}))

    total = summary.get("total_requests", 0)

    out.append("# HELP andromeda_requests_total Número total de peticiones en la ventana.")
    out.append("# TYPE andromeda_requests_total counter")
    out.append(_line("andromeda_requests_total", total))

    if total:
        sr = summary.get("success_rate_pct", summary.get("success_rate", 0))
        out.append("# HELP andromeda_success_rate Porcentaje de peticiones con éxito.")
        out.append("# TYPE andromeda_success_rate gauge")
        out.append(_line("andromeda_success_rate", round(sr, 2)))

        out.append("# HELP andromeda_latency_ms Latencia de respuesta (ms).")
        out.append("# TYPE andromeda_latency_ms summary")
        out.append(_line("andromeda_latency_ms", round(summary.get("p50_latency_ms", summary.get("avg_latency_ms", 0)), 1), {"quantile": "0.5"}))
        out.append(_line("andromeda_latency_ms", round(summary.get("p95_latency_ms", 0), 1), {"quantile": "0.95"}))
        out.append(_line("andromeda_latency_ms", round(summary.get("p99_latency_ms", 0), 1), {"quantile": "0.99"}))

        out.append("# HELP andromeda_degradation_rate Porcentaje de peticiones degradadas.")
        out.append("# TYPE andromeda_degradation_rate gauge")
        out.append(_line("andromeda_degradation_rate", round(summary.get("degradation_rate", 0), 2)))

    # Herramientas MCP
    by_tool = (tools or {}).get("by_tool", {})
    if by_tool:
        out.append("# HELP andromeda_tool_calls_total Llamadas por herramienta MCP.")
        out.append("# TYPE andromeda_tool_calls_total counter")
        for tool, d in by_tool.items():
            out.append(_line("andromeda_tool_calls_total", d.get("calls", 0), {"tool": tool}))
        out.append("# HELP andromeda_tool_error_rate Tasa de error por herramienta.")
        out.append("# TYPE andromeda_tool_error_rate gauge")
        for tool, d in by_tool.items():
            out.append(_line("andromeda_tool_error_rate", d.get("error_rate", 0), {"tool": tool}))

    # Experimentos A/B (si hay)
    if ab:
        out.append("# HELP andromeda_ab_requests_total Peticiones servidas por variante A/B.")
        out.append("# TYPE andromeda_ab_requests_total counter")
        for exp_id, exp in ab.items():
            for variant, stats in exp.get("variants", {}).items():
                out.append(_line("andromeda_ab_requests_total", stats.get("requests", 0),
                                 {"experiment": exp_id, "variant": variant}))
                out.append(_line("andromeda_ab_success_rate", round(stats.get("success_rate", 0), 2),
                                 {"experiment": exp_id, "variant": variant}))

    return "\n".join(out) + "\n"
