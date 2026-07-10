"""
mlops.py — Endpoints de MLOps de Andromeda.

Endpoints:
  GET /api/mlops/summary          → resumen de experiments y model registry
  GET /api/mlops/models/{id}      → comparación de modelos para un especialista
  GET /api/mlops/runs             → últimos N runs con métricas
  POST /api/mlops/eval            → lanzar una evaluación manual de un especialista
"""

import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.mlops")

router = APIRouter()


@router.get("/summary")
async def get_mlops_summary(request: Request) -> JSONResponse:
    """
    Resumen del experiment tracking:
    - Total de runs, success rate, avg latencia
    - Distribución de estrategias
    - Model registry (qué modelos han funcionado mejor)
    - Si MLflow está activo o no
    """
    tracker = getattr(request.app.state, "mlops_tracker", None)
    summary = tracker.get_experiment_summary()
    return JSONResponse(content=summary)


@router.get("/models/{specialist_id}")
async def get_model_comparison(specialist_id: str, request: Request) -> JSONResponse:
    """
    Compara el rendimiento de diferentes modelos para un especialista.
    Muy útil para decidir qué modelo poner en specialists.yaml.

    Ejemplo de respuesta:
    [
      {"model_name": "qwen2.5-coder:7b", "avg_latency_ms": 8200, "success_rate": 98.5},
      {"model_name": "phi3.5:3.8b",      "avg_latency_ms": 3100, "success_rate": 96.0}
    ]
    """
    tracker = getattr(request.app.state, "mlops_tracker", None)
    comparison = tracker.get_model_comparison(specialist_id)

    if not comparison:
        return JSONResponse(content={
            "specialist_id": specialist_id,
            "message": "Sin datos de uso para este especialista todavía.",
            "models": [],
        })

    return JSONResponse(content={
        "specialist_id": specialist_id,
        "models": comparison,
        "recommendation": comparison[0]["model_name"] if comparison else None,
    })


@router.get("/runs")
async def get_runs(request: Request, limit: int = 20) -> JSONResponse:
    """
    Últimos N runs del tracker de experimentos.
    Cada run corresponde a una petición del chat.
    """
    import sqlite3
    tracker = getattr(request.app.state, "mlops_tracker", None)

    try:
        conn = sqlite3.connect(tracker.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT r.run_id, r.request_id, r.start_time, r.end_time,
                   r.status, r.strategy, r.hardware_tier, r.degraded,
                   r.prompt_preview,
                   GROUP_CONCAT(CASE WHEN m.metric_name='latency_ms' THEN m.metric_value END) as latency_ms,
                   GROUP_CONCAT(CASE WHEN m.metric_name='success' THEN m.metric_value END) as success
            FROM runs r
            LEFT JOIN metrics m ON r.run_id = m.run_id
            GROUP BY r.run_id
            ORDER BY r.start_time DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        return JSONResponse(content={
            "runs": [dict(r) for r in rows],
            "count": len(rows),
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/eval/{specialist_id}")
async def eval_specialist(specialist_id: str, request: Request) -> JSONResponse:
    """
    Lanza una evaluación rápida de un especialista con prompts de referencia.
    Útil para comparar calidad antes/después de cambiar el modelo.

    Retorna: latencia, longitud de respuesta, y si el modelo sigue el formato esperado.
    """
    registry = request.app.state.registry
    settings = request.app.state.settings
    tracker = getattr(request.app.state, "mlops_tracker", None)

    # Validar que el especialista existe y está activo
    try:
        specialist = registry.get_by_id(specialist_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": f"Especialista '{specialist_id}' no encontrado"})

    if not registry.is_configured(specialist_id):
        return JSONResponse(status_code=400, content={"error": "Especialista no configurado"})

    # Prompts de evaluación por especialista
    eval_prompts = {
        "software-engineering": "Review this Python code for bugs:\ndef divide(a, b):\n    return a / b",
        "it-ops": "How do I check which process is using port 8080 on Linux?",
        "technical-writer": "Write a one-paragraph README description for a FastAPI REST API.",
        "verifier": "Verify this statement: 'Python lists are thread-safe for append operations.'",
        "summarizer": "Summarize in 2 bullet points: Andromeda is an AI orchestration platform that coordinates specialist models and adapts to hardware.",
        "generalist": "What is the difference between a process and a thread?",
    }

    prompt = eval_prompts.get(specialist_id, "Respond in one sentence: what is your specialty?")

    # Ejecutar evaluación
    run_id = tracker.start_run(
        request_id=str(uuid.uuid4()),
        prompt_preview=f"[EVAL] {prompt[:80]}",
        strategy="single",
        hardware_tier=request.app.state.hardware.max_tier,
    )

    t_start = time.perf_counter()
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": specialist.model_name,
                    "messages": [
                        {"role": "system", "content": specialist.system_prompt[:500]},
                        {"role": "user", "content": prompt},
                    ],
                    "options": {"temperature": 0.1, "num_predict": 300},
                    "stream": False,
                },
                timeout=60.0,
            )
            resp.raise_for_status()

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        latency_ms = round((time.perf_counter() - t_start) * 1000, 0)

        tracker.log_metrics(run_id, {"latency_ms": latency_ms, "success": 1.0, "response_length": len(content)})
        tracker.update_model_registry(
            specialist_id=specialist_id,
            model_name=specialist.model_name,
            hardware_tier=request.app.state.hardware.max_tier,
            latency_ms=latency_ms,
            success=True,
        )
        tracker.end_run(run_id, success=True)

        return JSONResponse(content={
            "specialist_id": specialist_id,
            "model_name": specialist.model_name,
            "eval_prompt": prompt,
            "response_preview": content[:400],
            "latency_ms": latency_ms,
            "response_length": len(content),
            "success": True,
            "run_id": run_id,
        })

    except Exception as exc:
        latency_ms = round((time.perf_counter() - t_start) * 1000, 0)
        tracker.log_metrics(run_id, {"latency_ms": latency_ms, "success": 0.0})
        tracker.end_run(run_id, success=False)
        return JSONResponse(status_code=503, content={"success": False, "error": str(exc)})


@router.get("/percentiles")
async def latency_percentiles(request: Request) -> JSONResponse:
    """Percentiles de latencia p50/p90/p95/p99."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"error": "MLOps no disponible"})
    return JSONResponse(content=tracker.get_latency_percentiles())


@router.get("/timeseries")
async def timeseries(metric: str = "latency_ms", request: Request = None) -> JSONResponse:
    """Serie temporal de una métrica para gráficos de tendencia."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"series": []})
    return JSONResponse(content={"series": tracker.get_timeseries(metric)})


@router.get("/models-used")
async def models_used(request: Request) -> JSONResponse:
    """Lista todos los modelos usados con sus métricas agregadas."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"models": []})
    return JSONResponse(content={"models": tracker.get_all_models_used()})


@router.get("/drift")
async def drift(metric: str = "latency_ms", request: Request = None) -> JSONResponse:
    """Detección de drift en una métrica."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"drift_detected": False})
    return JSONResponse(content=tracker.detect_drift(metric))


@router.get("/errors")
async def error_breakdown(request: Request) -> JSONResponse:
    """Desglose de errores por estrategia y tier."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"by_strategy": [], "by_tier": []})
    return JSONResponse(content=tracker.get_error_breakdown())


@router.get("/throughput")
async def throughput(request: Request) -> JSONResponse:
    """Throughput: runs por hora/día."""
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return JSONResponse(content={"total": 0, "last_hour": 0, "last_day": 0})
    return JSONResponse(content=tracker.get_throughput())


@router.get("/export/csv")
async def export_csv(request: Request):
    """Exporta runs a CSV descargable."""
    from fastapi.responses import PlainTextResponse
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return PlainTextResponse("error: MLOps no disponible")
    return PlainTextResponse(
        tracker.export_csv(),
        headers={"Content-Disposition": "attachment; filename=andromeda_mlops.csv"},
    )


@router.get("/export/prometheus")
async def export_prometheus(request: Request):
    """Exporta métricas en formato Prometheus."""
    from fastapi.responses import PlainTextResponse
    tracker = getattr(request.app.state, "mlops_tracker", None)
    if not tracker:
        return PlainTextResponse("# error: MLOps no disponible")
    return PlainTextResponse(tracker.export_prometheus())
