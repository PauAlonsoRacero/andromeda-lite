"""
policy.py — Policy Engine v2 de Andromeda.

NUEVO: Cálculo real de VRAM basado en niveles de modelos activos.
El engine ahora sabe exactamente cuánta VRAM consume cada modelo
y calcula dinámicamente cuántas IAs caben en paralelo.

Políticas de paralelismo:
  auto         — el sistema decide (máximo posible sin degradar calidad)
  max2         — nunca más de 2 IAs (política conservadora, ahorra VRAM)
  max1         — solo 1 IA (velocidad máxima, latencia mínima)
  max_hardware — todas las que quepan físicamente en el hardware

La política 'max2' es especialmente útil cuando:
  - El hardware está al límite
  - Se quiere calidad sin sobrecarga
  - Más de 2 respuestas no añaden valor perceptible al usuario
"""

import logging
from pathlib import Path

import yaml

from app.hardware.detector import HardwareDetector
from app.models.schemas import (
    ChatRequest,
    HardwareInfo,
    HardwarePolicy,
    RuntimePolicy,
    SpecialistProfile,
)

logger = logging.getLogger("andromeda.policy")

HEAVY_STRATEGIES = {"confidence_weighted", "quality_first", "iterative_refine"}

# VRAM overhead del sistema (Ollama + OS + buffer seguridad)
SYSTEM_VRAM_OVERHEAD_GB = 2.0

_FALLBACK_POLICIES: dict[int, dict] = {
    1: {
        "max_parallel": 1, "recommended_quant": "Q4_K_M",
        "max_context_tokens": 2048, "strategy_budget": "conservative",
        "can_run_verifier": False, "safe_vram_threshold_gb": 2.0,
        "eligible_strategies": ["single", "latency_first", "hardware_aware_fallback"],
    },
    2: {
        "max_parallel": 2, "recommended_quant": "Q5_K_M",
        "max_context_tokens": 4096, "strategy_budget": "balanced",
        "can_run_verifier": True, "safe_vram_threshold_gb": 6.0,
        "eligible_strategies": [
            "single", "iterative_refine", "verifier_pass",
            "latency_first", "hardware_aware_fallback",
        ],
    },
    3: {
        "max_parallel": 3, "recommended_quant": "Q8_0",
        "max_context_tokens": 8192, "strategy_budget": "aggressive",
        "can_run_verifier": True, "safe_vram_threshold_gb": 10.0,
        "eligible_strategies": [
            "single", "iterative_refine", "verifier_pass",
            "confidence_weighted", "quality_first",
            "latency_first", "hardware_aware_fallback",
        ],
    },
    4: {
        "max_parallel": 4, "recommended_quant": "fp16",
        "max_context_tokens": 16384, "strategy_budget": "aggressive",
        "can_run_verifier": True, "safe_vram_threshold_gb": 20.0,
        "eligible_strategies": [
            "single", "iterative_refine", "verifier_pass",
            "confidence_weighted", "quality_first",
            "latency_first", "hardware_aware_fallback",
        ],
    },
}

# VRAM estimada por nivel cuando no hay registry disponible
LEVEL_VRAM_ESTIMATE = {
    "low":   3.5,
    "mid":   8.0,
    "high":  20.0,
    "ultra": 48.0,
    "custom": 5.0,
}


class PolicyEngine:

    def __init__(self, config_path: str) -> None:
        self._detector = HardwareDetector()
        self._policies = self._load_policies(config_path)
        logger.info(f"PolicyEngine v2 inicializado. Tiers: {list(self._policies.keys())}")

    def _load_policies(self, config_path: str) -> dict[int, dict]:
        path = Path(config_path)
        if not path.exists():
            logger.warning("hardware_policies.yaml no encontrado. Usando defaults.")
            return _FALLBACK_POLICIES
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            policies = {}
            for key, value in data.items():
                if key.startswith("tier_"):
                    policies[int(key.split("_")[1])] = value
            return policies or _FALLBACK_POLICIES
        except Exception as exc:
            logger.error(f"Error leyendo hardware_policies.yaml: {exc}")
            return _FALLBACK_POLICIES

    def get_policy(self, hardware: HardwareInfo) -> HardwarePolicy:
        tier = hardware.max_tier
        data = self._policies.get(tier, self._policies.get(1, _FALLBACK_POLICIES[1]))
        return HardwarePolicy(
            tier=tier,
            max_parallel=data["max_parallel"],
            recommended_quant=data["recommended_quant"],
            max_context_tokens=data["max_context_tokens"],
            strategy_budget=data["strategy_budget"],
            can_run_verifier=data["can_run_verifier"],
            safe_vram_threshold_gb=data["safe_vram_threshold_gb"],
            eligible_strategies=data["eligible_strategies"],
        )

    def derive_runtime_policy(
        self,
        hardware: HardwareInfo,
        request: ChatRequest,
        available_specialists: list[SpecialistProfile],
        base_policy: HardwarePolicy | None = None,
        registry=None,
    ) -> RuntimePolicy:
        """
        Deriva la política de ejecución para este request concreto.

        Novedades v2:
          - Calcula VRAM real necesaria según niveles de modelos activos
          - Respeta parallel_policy del request (auto/max2/max1/max_hardware)
          - Respeta max_parallel del request (override manual)
          - Respeta specialist_levels del request (override de nivel por IA)
        """
        if base_policy is None:
            base_policy = self.get_policy(hardware)

        vram_free = self._detector.get_current_vram_free()
        # En CPU-only vram_free = 0, usar RAM como proxy
        if vram_free == 0 and hardware.acceleration == "cpu":
            vram_free = hardware.ram_available_gb * 0.5

        # ── 1. Límite de paralelismo según política y request ─────────────────
        parallel_policy = getattr(request, 'parallel_policy', 'auto')
        req_max_parallel = getattr(request, 'max_parallel', None)

        # Calcular techo máximo según política
        if parallel_policy == "max1":
            policy_cap = 1
        elif parallel_policy == "max2":
            policy_cap = 2
        elif parallel_policy == "max_hardware":
            policy_cap = base_policy.max_parallel
        else:  # auto
            policy_cap = base_policy.max_parallel

        # El usuario puede reducir adicionalmente con max_parallel
        if req_max_parallel is not None:
            policy_cap = min(policy_cap, req_max_parallel)

        # ── 2. Calcular cuántas IAs caben según VRAM real ─────────────────────
        specialist_levels = getattr(request, 'specialist_levels', {}) or {}
        vram_budget = max(0, vram_free - SYSTEM_VRAM_OVERHEAD_GB)

        # Si el usuario fuerza N IAs, priorizar CUMPLIR el recuento bajando
        # niveles (reparto del presupuesto), en vez de 1 IA grande.
        prefer_count = bool(req_max_parallel and req_max_parallel >= 2)
        selected, total_vram_needed, level_used = self._fit_specialists_to_vram(
            specialists=available_specialists,
            max_count=policy_cap,
            vram_budget_gb=vram_budget,
            registry=registry,
            hardware_tier=hardware.max_tier,
            specialist_level_overrides=specialist_levels,
            prefer_count=prefer_count,
        )

        # ── 3. Degradación si no hay VRAM suficiente para ninguna IA ─────────
        if not selected:
            reason = (
                f"VRAM libre insuficiente ({vram_free:.1f}GB) para cualquier modelo. "
                f"Usando el especialista más ligero disponible."
            )
            logger.warning(f"[DEGRADACIÓN CRÍTICA] {reason}")
            # Forzar el especialista más ligero
            if available_specialists:
                selected = [available_specialists[0]]
                total_vram_needed = 3.0
            else:
                return RuntimePolicy(
                    effective_parallel=0,
                    effective_strategy="single",
                    effective_specialists=[],
                    degraded=True,
                    degradation_reason="Sin especialistas disponibles",
                    vram_free_gb=vram_free,
                    hardware_tier=hardware.max_tier,
                    policy_name=f"T{hardware.max_tier}_no_specialists",
                )

        # ── 4. Degradación preventiva (VRAM baja pero funcional) ─────────────
        degraded = False
        degradation_reason = None
        threshold = base_policy.safe_vram_threshold_gb

        if vram_free > 0 and vram_free < threshold:
            degraded = True
            degradation_reason = (
                f"VRAM libre {vram_free:.1f}GB < umbral {threshold:.1f}GB. "
                f"Reducido a {len(selected)} especialista(s) con niveles más bajos."
            )
            logger.warning(f"[DEGRADACIÓN PREVENTIVA] {degradation_reason}")

        # ── 5. Determinar estrategia ──────────────────────────────────────────
        strategy = getattr(request, 'strategy', 'auto')
        if strategy == 'auto' or not strategy:
            strategy = self._default_strategy(hardware.max_tier, len(selected), base_policy)

        if strategy not in base_policy.eligible_strategies:
            strategy = base_policy.eligible_strategies[0] if base_policy.eligible_strategies else "single"

        effective_specialists = [s.id for s in selected]
        policy_name = f"T{hardware.max_tier}_{parallel_policy}_{len(selected)}x"

        logger.info(
            f"RuntimePolicy: {len(selected)} IAs [{', '.join(effective_specialists)}] "
            f"| estrategia={strategy} | VRAM={vram_free:.1f}GB libre "
            f"| necesita={total_vram_needed:.1f}GB | política={parallel_policy} "
            f"| niveles={level_used}"
        )

        return RuntimePolicy(
            effective_parallel=len(selected),
            effective_strategy=strategy,
            effective_specialists=effective_specialists,
            degraded=degraded,
            degradation_reason=degradation_reason,
            vram_free_gb=vram_free,
            hardware_tier=hardware.max_tier,
            policy_name=policy_name,
        )

    def _fit_specialists_to_vram(
        self,
        specialists: list[SpecialistProfile],
        max_count: int,
        vram_budget_gb: float,
        registry,
        hardware_tier: int,
        specialist_level_overrides: dict[str, str],
        prefer_count: bool = False,
    ) -> tuple[list[SpecialistProfile], float, dict[str, str]]:
        """
        Selecciona las IAs que caben en la VRAM disponible.

        Algoritmo:
          1. Para cada especialista, determinar qué nivel usará
             (override manual > automático por tier)
          2. Obtener el VRAM real de ese nivel del registry
          3. Añadir especialistas de mayor a menor prioridad
             mientras quepan en el presupuesto de VRAM

        Returns:
            (lista de especialistas seleccionados, VRAM total necesaria, niveles usados)
        """
        selected = []
        total_vram = 0.0
        levels_used = {}

        for spec in specialists:
            if len(selected) >= max_count:
                break

            # Determinar nivel y VRAM de este especialista
            # prefer_count: cada IA elige nivel dentro de su CUOTA del
            # presupuesto (budget/N) para que quepan todas las pedidas.
            if prefer_count and max_count >= 2:
                slot_budget = min(vram_budget_gb - total_vram, vram_budget_gb / max_count)
            else:
                slot_budget = vram_budget_gb - total_vram
            vram_needed, level_name = self._get_specialist_vram(
                specialist_id=spec.id,
                registry=registry,
                hardware_tier=hardware_tier,
                vram_free=slot_budget,
                override_level=specialist_level_overrides.get(spec.id),
            )

            if total_vram + vram_needed <= vram_budget_gb:
                selected.append(spec)
                total_vram += vram_needed
                levels_used[spec.id] = level_name
                logger.debug(
                    f"  ✓ {spec.id} ({level_name}, {vram_needed:.1f}GB) "
                    f"→ total {total_vram:.1f}/{vram_budget_gb:.1f}GB"
                )
            else:
                # No cabe con el nivel actual — intentar bajar nivel
                lower_vram, lower_level = self._get_specialist_vram(
                    specialist_id=spec.id,
                    registry=registry,
                    hardware_tier=hardware_tier,
                    vram_free=vram_budget_gb - total_vram,
                    override_level="low",  # Forzar al nivel más bajo
                )
                if total_vram + lower_vram <= vram_budget_gb:
                    selected.append(spec)
                    total_vram += lower_vram
                    levels_used[spec.id] = f"{lower_level}↓"  # ↓ indica que se bajó el nivel
                    logger.info(
                        f"  ↓ {spec.id} bajado a {lower_level} ({lower_vram:.1f}GB) "
                        f"por falta de VRAM"
                    )
                else:
                    logger.debug(
                        f"  ✗ {spec.id} no cabe ni en nivel low "
                        f"({lower_vram:.1f}GB > presupuesto restante "
                        f"{vram_budget_gb - total_vram:.1f}GB)"
                    )

        return selected, total_vram, levels_used

    def _get_specialist_vram(
        self,
        specialist_id: str,
        registry,
        hardware_tier: int,
        vram_free: float,
        override_level: str | None = None,
    ) -> tuple[float, str]:
        """
        Retorna (vram_needed_gb, level_name) para un especialista.
        Usa el registry si está disponible, sino usa estimaciones.
        """
        if registry is None:
            return (LEVEL_VRAM_ESTIMATE.get("mid", 5.0), "mid")

        try:
            if override_level:
                tiers = registry.get_tiers(specialist_id)
                if tiers:
                    level = tiers.level_for_name(override_level)
                    if level:
                        return (level.vram_required_gb, override_level)

            model_name, level_name = registry.resolve_model_for_tier(
                specialist_id, hardware_tier, vram_free
            )
            tiers = registry.get_tiers(specialist_id)
            if tiers:
                level = tiers.level_for_name(level_name.rstrip("↓"))
                if level:
                    return (level.vram_required_gb, level_name)

            # Fallback a estimación por nivel
            return (LEVEL_VRAM_ESTIMATE.get(level_name, 5.0), level_name)

        except Exception as exc:
            logger.debug(f"Error obteniendo VRAM de {specialist_id}: {exc}")
            # Usar VRAM del profile como fallback
            profile = None
            try:
                profile = registry.get_by_id(specialist_id)
            except Exception:
                pass
            vram = profile.vram_required_gb if profile else 5.0
            return (vram, "custom")

    def _default_strategy(
        self, tier: int, num_specialists: int, policy: HardwarePolicy
    ) -> str:
        """Estrategia por defecto según tier y número de IAs."""
        if num_specialists == 1:
            return "single"
        if num_specialists == 2:
            if "iterative_refine" in policy.eligible_strategies:
                return "iterative_refine"
            return "vote"
        # 3+ IAs
        if "confidence_weighted" in policy.eligible_strategies:
            return "confidence_weighted"
        return "synthesis"

    def get_vram_breakdown(
        self, specialists: list[SpecialistProfile], registry, hardware_tier: int, vram_free: float
    ) -> list[dict]:
        """
        Retorna un desglose de VRAM por especialista.
        Útil para la UI — mostrar cuánta VRAM usa cada IA.
        """
        result = []
        for spec in specialists:
            vram, level = self._get_specialist_vram(
                spec.id, registry, hardware_tier, vram_free
            )
            result.append({
                "specialist_id": spec.id,
                "level":         level,
                "vram_gb":       vram,
                "model_name":    getattr(spec, "model_name", ""),
            })
        return result
