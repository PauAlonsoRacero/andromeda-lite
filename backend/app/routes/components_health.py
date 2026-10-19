"""
components_health.py — Estado de cada subsistema de Andromeda.

Las analíticas existentes miden peticiones (latencia, errores, calidad). Esto
mide algo distinto y complementario: si cada PIEZA de la aplicación está viva y
qué está haciendo. Sirve para responder "¿por qué no me funciona X?" de un
vistazo, sin bucear en logs.

Cada componente reporta: estado (ok / degradado / apagado / error), una métrica
principal legible y un detalle. Ningún fallo de un componente puede tumbar el
endpoint: cada sonda va en su propio try.
"""
from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.components")
router = APIRouter()

OK, DEGRADED, OFF, ERROR = "ok", "degraded", "off", "error"


def _probe(fn) -> dict:
    """Ejecuta una sonda aislando sus fallos."""
    try:
        return fn()
    except Exception as exc:                      # noqa: BLE001
        return {"status": ERROR, "metric": "—", "detail_key": "cd.probe_error",
                "detail_args": {"err": f"{type(exc).__name__}: {exc}"[:120]}}


@router.get("")
async def components(request: Request) -> JSONResponse:
    """Estado de todos los subsistemas."""
    app = request.app
    st = app.state
    t0 = time.perf_counter()

    def ollama():
        reg = getattr(st, "registry", None)
        models = list(getattr(reg, "available_models", []) or []) if reg else []
        if not models:
            return {"status": DEGRADED, "metric": "0 modelos", "metric_key": "chm.models", "metric_n": 0,
                    "detail_key": "cd.ollama_none"}

        # Variables que convienen en el servidor de Ollama y que Andromeda no
        # puede fijar por sí misma (pertenecen al proceso `ollama serve`). Si
        # faltan, se avisa: activarlas da bastante rendimiento gratis.
        faltan = []
        try:
            from app.core.inference_tuning import recommended_server_env
            hw = getattr(st, "hardware", None)
            recomendado = recommended_server_env(
                float(getattr(hw, "total_vram_gb", 0) or 0),
                str(getattr(hw, "acceleration", "") or ""),
            )
            faltan = [k for k, v in recomendado.items()
                      if os.environ.get(k, "").lower() not in (v.lower(), "true", "on")]
        except Exception:
            faltan = []

        if faltan:
            return {"status": OK, "metric": f"{len(models)} modelos", "metric_key": "chm.models", "metric_n": len(models),
                    "detail_key": "cd.ollama_tune",
                    "detail_args": {"vars": " ".join(faltan)}}
        return {"status": OK, "metric": f"{len(models)} modelos", "metric_key": "chm.models", "metric_n": len(models),
                "detail_key": "cd.ollama_ok", "detail_args": {"list": ", ".join(models[:4]) + ("…" if len(models) > 4 else "")}}

    def specialists():
        reg = getattr(st, "registry", None)
        active = reg.get_active() if reg else []
        configured = [s for s in active if getattr(s, "model_name", "")]
        if not configured:
            return {"status": DEGRADED, "metric": "0 activos", "metric_key": "chm.active", "metric_n": 0,
                    "detail_key": "cd.spec_none"}
        return {"status": OK, "metric": f"{len(configured)} activos", "metric_key": "chm.active", "metric_n": len(configured),
                "detail_key": "cd.spec_ok", "detail_args": {"list": ", ".join(s.id for s in configured[:4])}}

    def memory():
        store = getattr(st, "memory_store", None)
        if store is None:
            return {"status": OFF, "metric": "—", "detail_key": "cd.not_init"}
        stats = store.stats() if hasattr(store, "stats") else {}
        n = stats.get("total", stats.get("count", 0))
        return {"status": OK, "metric": f"{n} recuerdos", "metric_key": "chm.memories", "metric_n": n,
                "detail_key": "cd.memory_ok"}

    def rag():
        idx = getattr(st, "rag_index", None)
        if idx is None:
            return {"status": OFF, "metric": "—", "detail_key": "cd.not_init"}
        s = idx.stats()
        if not s["chunks"]:
            return {"status": OFF, "metric": "vacío", "metric_key": "chm.empty",
                    "detail_key": "cd.rag_empty"}
        return {"status": OK, "metric": f"{s['documents']} docs", "metric_key": "chm.docs", "metric_n": s["documents"],
                "detail_key": "cd.rag_ok", "detail_args": {"chunks": s["chunks"], "terms": s["terms"]}}

    def skills():
        reg = getattr(st, "skill_registry", None)
        if reg is None:
            return {"status": OFF, "metric": "—", "detail": "No inicializado."}
        total = len(reg.skills)
        mine = sum(1 for s in reg.skills.values() if getattr(s, "user_created", False))
        return {"status": OK, "metric": f"{total} skills", "metric_key": "chm.skills", "metric_n": total,
                "detail_key": "cd.skills_ok", "detail_args": {"builtin": total - mine, "mine": mine}}

    def mcp():
        mgr = getattr(st, "mcp_manager", None)
        if mgr is None:
            return {"status": OFF, "metric": "—", "detail": "No inicializado."}
        summary = mgr.get_tools_summary()
        servers = summary.get("servers", {}) or {}
        connected = [s for s in servers.values() if s.get("connected")]
        tools = sum(s.get("count", 0) for s in connected)
        if not connected:
            return {"status": OFF, "metric": "0 conectados", "metric_key": "chm.connected", "metric_n": 0,
                    "detail_key": "cd.mcp_none"}
        return {"status": OK, "metric": f"{len(connected)} conectados", "metric_key": "chm.connected", "metric_n": len(connected),
                "detail_key": "cd.mcp_ok", "detail_args": {"tools": tools}}

    def web():
        from app.core.flags import get_flag
        on = get_flag(getattr(st, "settings", None), "andromeda_network_egress")
        return {"status": OK if on else OFF,
                "metric": "activada" if on else "desactivada", "metric_key": "chm.on" if on else "chm.off",
                "detail_key": ("cd.web_on" if on else "cd.web_off")}

    def registry_mlops():
        reg = getattr(st, "model_registry", None)
        if reg is None:
            return {"status": OFF, "metric": "—", "detail": "No inicializado."}
        prod = reg.production() if hasattr(reg, "production") else None
        if not prod:
            return {"status": OFF, "metric": "sin producción", "metric_key": "chm.no_prod",
                    "detail_key": "cd.reg_none"}
        return {"status": OK, "metric": getattr(prod, "version", "?"),
                "detail_key": "cd.reg_ok", "detail_args": {"model": getattr(prod, "model_name", "?")}}

    def ab():
        t = getattr(st, "ab_testing", None)
        if t is None:
            return {"status": OFF, "metric": "—", "detail": "No inicializado."}
        exp = t.active_experiment() if hasattr(t, "active_experiment") else None
        if not exp:
            return {"status": OFF, "metric": "sin experimentos", "metric_key": "chm.no_exp",
                    "detail_key": "cd.ab_none"}
        return {"status": OK, "metric": exp.get("name", "activo"),
                "detail_key": "cd.ab_ok"}

    def feedback():
        store = getattr(st, "feedback_store", None)
        if store is None:
            return {"status": OFF, "metric": "—", "detail": "No inicializado."}
        s = store.stats() if hasattr(store, "stats") else {}
        total = s.get("total", 0)
        if not total:
            return {"status": OFF, "metric": "sin votos", "metric_key": "chm.no_votes",
                    "detail_key": "cd.fb_none"}
        return {"status": OK, "metric": f"{s.get('satisfaction', 0):.0f}% satisfacción", "metric_key": "chm.satisfaction", "metric_n": round(s.get("satisfaction", 0) or 0),
                "detail_key": "cd.fb_ok", "detail_args": {"up": s.get("up", 0), "down": s.get("down", 0)}}

    def workspace():
        path = os.environ.get("ANDROMEDA_WORKSPACE", "")
        if not path or not os.path.isdir(path):
            return {"status": OFF, "metric": "—", "detail_key": "cd.ws_none"}
        try:
            n = len([f for f in os.listdir(path) if not f.startswith(".")])
        except OSError:
            n = 0
        return {"status": OK, "metric": f"{n} archivos", "metric_key": "chm.files", "metric_n": n, "detail_key": "cd.ws_ok", "detail_args": {"path": path}}

    # "Especialistas" es un concepto de la edición Pro (varias IAs con roles
    # distintos respondiendo en paralelo). En Lite hay un solo modelo, así que
    # mostrar la tarjeta solo genera confusión sobre algo que no existe aquí.
    from app.editions import orchestration_enabled

    result = {
        "ollama":      _probe(ollama),
        "memory":      _probe(memory),
        "rag":         _probe(rag),
        "skills":      _probe(skills),
        "mcp":         _probe(mcp),
        "web_search":  _probe(web),
        "registry":    _probe(registry_mlops),
        "ab_testing":  _probe(ab),
        "feedback":    _probe(feedback),
        "workspace":   _probe(workspace),
    }
    if orchestration_enabled():
        result["specialists"] = _probe(specialists)

    healthy = sum(1 for c in result.values() if c["status"] == OK)
    return JSONResponse(content={
        "components": result,
        "healthy": healthy,
        "total": len(result),
        "probe_ms": round((time.perf_counter() - t0) * 1000, 1),
    })
