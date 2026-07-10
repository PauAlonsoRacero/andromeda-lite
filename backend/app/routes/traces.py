"""
traces.py — Endpoints de observabilidad de Andromeda.

Endpoints:
  GET /api/traces              → últimos N traces
  GET /api/traces/metrics      → estadísticas agregadas
  GET /api/traces/{request_id} → trace completo de un request
  DELETE /api/traces           → borrar todos (solo en development)
"""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.traces")

router = APIRouter()


@router.get("")
async def get_traces(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200, description="Número de traces a retornar"),
) -> JSONResponse:
    """
    Retorna los últimos N traces ordenados por timestamp descendente.

    Cada trace incluye: request_id, timestamp, estrategia, especialistas,
    latencia, TTFT, tier de hardware, si hubo degradación y el reasoning.
    """
    store = getattr(request.app.state, "store", None)
    if store is None or not hasattr(store, "get_recent"):
        return JSONResponse(content={"traces": [], "count": 0, "limit": limit})
    traces = await store.get_recent(limit=limit)
    return JSONResponse(content={
        "traces": traces,
        "count": len(traces),
        "limit": limit,
    })


@router.get("/metrics")
async def get_metrics(request: Request) -> JSONResponse:
    """
    Retorna estadísticas agregadas calculadas desde dos fuentes:
      - MetricsCollector (en memoria, rápido, ventana deslizante)
      - TraceStore SQLite (persistente, más completo pero más lento)

    Incluye: latencias p50/p95/p99, success rate, degradation rate,
    distribución de estrategias y especialistas.
    """
    metrics = getattr(request.app.state, "metrics", None)
    tracer = getattr(request.app.state, "store", None)

    # Métricas en memoria (rápidas)
    memory_metrics = metrics.get_summary() if metrics is not None else {
        "total_requests": 0, "success_rate": 0, "avg_latency_ms": 0,
        "p50_ms": 0, "p95_ms": 0, "p99_ms": 0,
    }

    # Métricas históricas de SQLite — get_stats vive en el TraceStore,
    # que está dentro del tracer (tracer.store), no en el tracer mismo.
    store = getattr(tracer, "_store", None) or getattr(tracer, "store", None) or getattr(request.app.state, "trace_store", None)
    db_stats = {}
    if store is not None and hasattr(store, "get_stats"):
        try:
            db_stats = await store.get_stats()
        except Exception:
            db_stats = {}

    # Analytics de herramientas MCP (uso, latencia, error rate por herramienta)
    tool_metrics = {}
    if metrics is not None and hasattr(metrics, "get_tool_summary"):
        try:
            tool_metrics = metrics.get_tool_summary()
        except Exception:
            tool_metrics = {}

    return JSONResponse(content={
        "realtime": memory_metrics,
        "historical": db_stats,
        "tools": tool_metrics,
    })


@router.get("/quality/history")
async def quality_history(request: Request) -> JSONResponse:
    """Serie temporal de calidad + evaluación SLO + tendencia (drift).

    Al consultarse toma también una foto (como hace un scrape de Prometheus), así
    la serie crece aunque la app se use a ráfagas.
    """
    qh = getattr(request.app.state, "quality_history", None)
    if qh is None:
        return JSONResponse(content={"points": [], "assessment": {}})
    try:
        m = request.app.state.metrics.get_summary()
        fb = request.app.state.feedback_store.stats() if getattr(request.app.state, "feedback_store", None) else {}
        qh.snapshot(m, fb.get("satisfaction"))
    except Exception:
        pass
    return JSONResponse(content={"points": qh.series(), "assessment": qh.assess_slo()})
async def get_trace(request_id: str, request: Request) -> JSONResponse:
    """
    Retorna el trace completo de un request específico.

    Incluye el árbol de spans completo con tiempos de cada componente:
    classifier, executor (por especialista), merger.

    Args:
        request_id: UUID del request a buscar
    """
    store = getattr(request.app.state, "store", None)
    if store is None:
        return JSONResponse(status_code=404, content={"error": True, "code": "NOT_FOUND", "message": "Trace store no disponible"})
    trace = await store.get_by_request_id(request_id)

    if trace is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": True,
                "code": "NOT_FOUND",
                "message": f"No se encontró trace para request_id '{request_id}'",
            },
        )

    return JSONResponse(content=trace)


@router.delete("")
async def delete_traces(request: Request) -> JSONResponse:
    """
    Borra todos los traces almacenados.
    Solo disponible en environment=development.
    """
    settings = request.app.state.settings

    if settings.environment != "development":
        return JSONResponse(
            status_code=403,
            content={
                "error": True,
                "code": "FORBIDDEN",
                "message": "DELETE solo disponible en environment=development",
            },
        )

    import sqlite3
    import asyncio

    store = getattr(request.app.state, "store", None)

    def _delete_all():
        conn = sqlite3.connect(store.db_path)
        cursor = conn.execute("DELETE FROM traces")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(None, _delete_all)

    # Limpiar también las métricas en memoria
    request.app.state.metrics._window.clear()

    return JSONResponse(content={
        "success": True,
        "deleted": deleted,
        "message": f"Se eliminaron {deleted} traces",
    })
