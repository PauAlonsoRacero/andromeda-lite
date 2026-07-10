"""orchestrator.py — STUB Lite. La orquestación multi-IA (paralelo + fusión)
es exclusiva de Pro. Lite usa linear_orchestrator.py (power-scaling de UNA IA)."""
from __future__ import annotations
import copy
import logging
from dataclasses import dataclass, field
logger = logging.getLogger("andromeda.orchestrator.lite")

@dataclass
class OrchestrationPlan:
    specialists: list; strategy: str; n_parallel: int; mode: str
    use_output_ai: bool; output_model: str | None; classifier_source: str
    reasoning: str; confidence: float; complexity: float = 0.0
    power_tier: int = 1; models_used: list = field(default_factory=list)

def build_plan(*, chat_request, active_specialists, classifier_result,
               runtime_policy, registry, hardware):
    """En Lite el plan siempre es una IA. La potencia la decide
    linear_orchestrator.decide_power() en el camino de chat.py."""
    from app.core.linear_orchestrator import decide_power, LEVELS
    base = None
    for s in active_specialists or []:
        if getattr(s, "id", None) == "generalist":
            base = copy.copy(s); break
    if base is None and active_specialists:
        base = copy.copy(active_specialists[0])
    if base is None:
        raise RuntimeError("No hay especialistas activos")

    fm = (getattr(chat_request, "force_model", None) or "").strip()
    if fm:
        base.model_name = fm
        tier_n = getattr(base, "tier", 1) or 1
        reason = "Lite: modelo forzado"
        score = 0.0
    else:
        tiers = registry._tiers.get(base.id) if registry else None
        avail = set()
        if tiers:
            for lv in LEVELS:
                o = getattr(tiers, lv, None)
                if o and getattr(o, "model_name", None):
                    avail.add(lv)
        levels = (getattr(chat_request, "specialist_levels", None) or {})
        choice = levels.get(base.id) or levels.get("generalist") or "auto"
        tmap = {1:"low",2:"mid",3:"high",4:"ultra"}
        hw_max = tmap.get(getattr(hardware, "max_tier", 4), "ultra")
        d = decide_power(getattr(chat_request,"prompt","") or "", user_choice=choice,
                         hardware_max_level=hw_max, available_levels=avail or None)
        o = getattr(tiers, d.level, None) if tiers else None
        if o and getattr(o, "model_name", None):
            base.model_name = o.model_name
        tier_n = {"low":1,"mid":2,"high":3,"ultra":4}.get(d.level, 1)
        reason = f"Andromeda Lite · {d.reason}"; score = d.score

    return OrchestrationPlan(specialists=[base], strategy="single", n_parallel=1,
        mode="fast", use_output_ai=False, output_model=None,
        classifier_source="lite-linear", reasoning=reason, confidence=1.0,
        complexity=max(score,0.0), power_tier=tier_n,
        models_used=[getattr(base,"model_name","") or ""])
