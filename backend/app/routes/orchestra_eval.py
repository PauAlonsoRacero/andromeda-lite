"""
orchestra_eval.py — Expone el banco de pruebas del enrutamiento vía API.

GET /api/orchestra/eval → métricas de calidad del enrutamiento (dominio,
especialista, tier) sobre los datasets de entrenamiento y validación.

Permite ver desde la UI cómo de bien decide Andromeda Orquesta, y sirve como
evidencia de rigor (evaluación medible, no a ojo).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.orchestra_eval")
router = APIRouter()

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@router.get("/eval")
async def routing_eval() -> JSONResponse:
    """Corre el banco de pruebas del enrutamiento y devuelve las métricas."""
    import sys
    eval_dir = _ROOT / "eval"
    if not eval_dir.exists():
        return JSONResponse(status_code=503,
                            content={"error": "Banco de pruebas no disponible"})
    sys.path.insert(0, str(eval_dir))
    try:
        from eval_routing import evaluate
        train = evaluate(eval_dir / "routing_dataset.jsonl")
        holdout = evaluate(eval_dir / "routing_holdout.jsonl")
        return JSONResponse(content={
            "train": {k: v for k, v in train.items() if k != "rows"},
            "holdout": {k: v for k, v in holdout.items() if k != "rows"},
        })
    except Exception as exc:
        logger.exception("Error corriendo el eval de enrutamiento")
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/explain")
async def explain_plan(request: Request) -> JSONResponse:
    """
    Explica qué haría el orquestador con un prompt, SIN ejecutarlo.

    POST /api/orchestra/explain  body: {"prompt": "..."}
    → dominio, complejidad, tier de potencia, especialista(s), estrategia.

    Útil para depurar el enrutamiento y para mostrar en vivo cómo decide
    Andromeda Orquesta (transparencia).
    """
    from app.core.orchestrator import build_plan, _detect_domain
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "Prompt vacío"})

    app = request.app
    registry = app.state.registry
    hardware = app.state.hardware
    runtime_policy = app.state.policy

    class _Req:
        def __init__(self, p):
            self.prompt = p; self.specialists = None
            self.strategy = "auto"; self.max_parallel = None

    try:
        active = registry.get_active()
        plan = build_plan(chat_request=_Req(prompt), active_specialists=active,
                          classifier_result=None, runtime_policy=runtime_policy,
                          registry=registry, hardware=hardware)
        domain = _detect_domain(prompt)
        return JSONResponse(content={
            "prompt": prompt[:200],
            "domain": domain,
            "complexity": round(plan.complexity, 3),
            "power_tier": plan.power_tier,
            "n_parallel": plan.n_parallel,
            "specialists": [s.id for s in plan.specialists],
            "models": plan.models_used,
            "strategy": plan.strategy,
            "mode": plan.mode,
            "use_output_ai": plan.use_output_ai,
            "reasoning": plan.reasoning,
        })
    except Exception as exc:
        logger.exception("Error explicando el plan")
        return JSONResponse(status_code=500, content={"error": str(exc)})
