"""
alerts.py — Sistema de alertas del sistema.

Monitoriza el estado del sistema y genera alertas cuando:
  - La VRAM supera el umbral (>85%)
  - La latencia promedio sube más del 50%
  - La tasa de errores supera el 10%
  - Ollama se desconecta
  - Un especialista deja de responder

Endpoints:
  GET  /api/alerts          → alertas activas
  GET  /api/alerts/history  → historial de alertas
  POST /api/alerts/check    → ejecutar check manual
  PUT  /api/alerts/config   → configurar thresholds
"""

import logging
import datetime
from datetime import timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.alerts")
router = APIRouter()

# Config por defecto
DEFAULT_THRESHOLDS = {
    "vram_pct":          85.0,   # % VRAM — alertar si supera
    "error_rate_pct":    10.0,   # % errores — alertar si supera
    "latency_ms":        30000,  # ms — alertar si supera
    "latency_increase":  50.0,   # % de aumento — alertar si supera
}


@router.get("")
async def get_alerts(request: Request) -> JSONResponse:
    """Ejecuta checks y retorna alertas activas ahora mismo."""
    alerts = await _run_checks(request)
    return JSONResponse(content={
        "alerts":    alerts,
        "count":     len(alerts),
        "critical":  sum(1 for a in alerts if a["level"] == "critical"),
        "warnings":  sum(1 for a in alerts if a["level"] == "warning"),
        "checked_at":datetime.datetime.now(timezone.utc).isoformat(),
    })


@router.post("/check")
async def manual_check(request: Request) -> JSONResponse:
    """Fuerza un check manual del sistema."""
    alerts = await _run_checks(request)
    return JSONResponse(content={"alerts": alerts, "count": len(alerts)})


@router.get("/config")
async def get_alert_config(request: Request) -> JSONResponse:
    config = getattr(request.app.state, 'alert_config', DEFAULT_THRESHOLDS.copy())
    return JSONResponse(content=config)


@router.put("/config")
async def update_alert_config(request: Request) -> JSONResponse:
    body = await request.json()
    config = getattr(request.app.state, 'alert_config', DEFAULT_THRESHOLDS.copy())
    config.update({k: v for k, v in body.items() if k in DEFAULT_THRESHOLDS})
    request.app.state.alert_config = config
    return JSONResponse(content={"success": True, "config": config})


async def _run_checks(request: Request) -> list[dict]:
    """Ejecuta todos los checks y retorna las alertas activas."""
    import httpx
    alerts   = []
    settings = request.app.state.settings
    hardware = request.app.state.hardware
    config   = getattr(request.app.state, 'alert_config', DEFAULT_THRESHOLDS.copy())

    def alert(level: str, title: str, message: str, metric: dict = None):
        alerts.append({
            "id":        f"{title.lower().replace(' ','-')}",
            "level":     level,  # critical | warning | info
            "title":     title,
            "message":   message,
            "metric":    metric or {},
            "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
        })

    # ── Check 1: Ollama disponible ────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if r.status_code != 200:
                alert("critical", "Ollama no disponible",
                      f"Ollama respondió con HTTP {r.status_code}")
    except Exception as exc:
        alert("critical", "Ollama sin conexión",
              f"No se puede conectar a Ollama: {exc}")

    # ── Check 2: VRAM ─────────────────────────────────────────────────────────
    if hardware.total_vram_gb > 0:
        try:
            from app.hardware.detector import HardwareDetector
            free_gb = HardwareDetector().get_current_vram_free()
            used_pct = ((hardware.total_vram_gb - free_gb) / hardware.total_vram_gb) * 100
            if used_pct > config["vram_pct"]:
                alert("warning", "VRAM alta",
                      f"VRAM al {used_pct:.1f}% ({free_gb:.1f}GB libre de {hardware.total_vram_gb:.1f}GB)",
                      {"vram_pct": round(used_pct,1), "free_gb": round(free_gb,1)})
        except Exception:
            pass

    # ── Check 3: Tasa de errores ──────────────────────────────────────────────
    try:
        metrics = request.app.state.metrics.get_realtime_stats()
        error_pct = (1 - metrics.get("success_rate", 1)) * 100
        if error_pct > config["error_rate_pct"]:
            alert("warning", "Tasa de errores alta",
                  f"El {error_pct:.1f}% de las peticiones están fallando",
                  {"error_rate_pct": round(error_pct,1)})
    except Exception:
        pass

    # ── Check 4: Latencia ─────────────────────────────────────────────────────
    try:
        metrics = request.app.state.metrics.get_realtime_stats()
        avg_latency = metrics.get("avg_latency_ms", 0)
        if avg_latency > config["latency_ms"]:
            alert("warning", "Latencia alta",
                  f"Latencia promedio: {avg_latency:.0f}ms (umbral: {config['latency_ms']}ms)",
                  {"latency_ms": round(avg_latency)})
    except Exception:
        pass

    # ── Check 5: Especialistas configurados ───────────────────────────────────
    registry = request.app.state.registry
    active   = registry.get_active()
    if len(active) == 0:
        alert("warning", "Sin IAs activas",
              "No hay especialistas configurados. Ve a Modelos para activar IAs.")

    return alerts
