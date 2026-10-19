"""
router.py — Pipeline end-to-end del orquestador de Andromeda.

Coordina todos los componentes del sistema para procesar un ChatRequest:
  1. Genera request_id y trace_id únicos
  2. Inicia el span de observabilidad
  3. Verifica que hay especialistas disponibles
  4. Deriva la política runtime (VRAM actual + tier)
  5. Clasifica la intención del prompt
  6. Ejecuta los especialistas (paralelo o serie)
  7. Fusiona los outputs con la estrategia
  8. Construye el ChatResponse con todos los metadatos
  9. Persiste el TraceRecord (en bloque finally — siempre se ejecuta)

Este módulo no tiene lógica de negocio propia — delega a cada componente.
Su responsabilidad es la coordinación y el manejo de errores de alto nivel.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from app.config import Settings
from app.core.executor import execute_specialists
from app.core.merger import merge_responses
from app.hardware.detector import HardwareDetector
from app.hardware.policy import PolicyEngine
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HardwareInfo,
    TraceRecord,
)
from app.observability.metrics import MetricsCollector
from app.mlops.tracker import MLOpsTracker
from app.observability.tracer import AndromedalTracer
from app.specialists.registry import SpecialistRegistry

logger = logging.getLogger("andromeda.router")

# Detector para medición de VRAM en tiempo real
_detector = HardwareDetector()


async def process_request(
    request: ChatRequest,
    registry: SpecialistRegistry,
    hardware: HardwareInfo,
    policy_engine: PolicyEngine,
    tracer: AndromedalTracer,
    metrics: MetricsCollector,
    settings: Settings,
    mlops_tracker: MLOpsTracker | None = None,
    memory_store=None,
    mcp_manager=None,
    memory_profile=None,
    rag_index=None,
    skill_registry=None,
) -> ChatResponse:
    """
    Pipeline completo de procesamiento de un ChatRequest.

    Args:
        request: Petición del usuario (prompt, strategy, etc.)
        registry: Catálogo de especialistas
        hardware: Info de hardware detectado al arranque
        policy_engine: Motor de políticas de hardware
        tracer: Sistema de trazabilidad
        metrics: Colector de métricas en memoria
        settings: Configuración global

    Returns:
        ChatResponse con la respuesta final y todos los metadatos

    Raises:
        No lanza excepciones — los errores se capturan y retornan como ChatResponse
        con success=False y un mensaje descriptivo.
    """
    # ── PASO 1: Identificadores únicos ────────────────────────────────────────
    request_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    t_start = time.perf_counter()
    t_first_token = None  # Se establecerá cuando llegue el primer token

    # Inicializar el trace que se irá completando durante el procesamiento
    trace = TraceRecord(
        trace_id=trace_id,
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        # Incógnito: nunca escribir el texto del usuario en disco.
        prompt_preview="" if request.incognito else request.prompt[:100],
        strategy=request.strategy,
    )

    # ── PASO 2: Iniciar span de observabilidad + MLOps run ───────────────────────
    tracer.start_span(request_id, "process_request")

    # Iniciar run de MLOps (tracking de experimentos)
    mlops_run_id = None
    if mlops_tracker:
        mlops_run_id = mlops_tracker.start_run(
            request_id=request_id,
            prompt_preview=request.prompt[:100],
            strategy=request.strategy,
            hardware_tier=hardware.max_tier,
        )

    try:
        # ── PASO 3: Verificar especialistas disponibles ───────────────────────
        active_specialists = registry.get_eligible_for_tier(hardware.max_tier)
        # Si no queda ninguna IA activa pero hay modelos instalados (p. ej. se pulsó
        # "Desactivar" en Modelos), se usa la general: en Lite hay una sola, y
        # desactivarla dejaba el chat inservible con un aviso engañoso
        # ("descarga un modelo" teniendo diez instalados).
        if not active_specialists:
            active_specialists = registry.fallback_specialists(hardware.max_tier)

        if not active_specialists:
            status = registry.get_status_summary()
            error_msg = (
                f"No hay especialistas activos configurados. "
                f"Estado: {status['active']}/{status['total']} activos, "
                f"{status['pending']} pendientes. "
                f"Edita config/specialists.yaml y asigna modelos Ollama."
            )
            logger.warning(error_msg)
            return _error_response(request_id, trace_id, error_msg)

        tracer.add_event(request_id, "specialists_available", {
            "count": len(active_specialists),
            "ids": [s.id for s in active_specialists],
        })

        # ── PASO 4: Derivar política runtime ─────────────────────────────────
        # Combina la política base del tier con la VRAM libre AHORA
        base_policy = policy_engine.get_policy(hardware)
        runtime_policy = policy_engine.derive_runtime_policy(
            hardware=hardware,
            request=request,
            available_specialists=active_specialists,
            base_policy=base_policy,
            registry=registry,
        )

        tracer.add_event(request_id, "policy_applied", {
            "tier": runtime_policy.hardware_tier,
            "policy": runtime_policy.policy_name,
            "effective_parallel": runtime_policy.effective_parallel,
            "effective_strategy": runtime_policy.effective_strategy,
            "degraded": runtime_policy.degraded,
            "vram_free_gb": runtime_policy.vram_free_gb,
        })
        # Construcción del prompt: un único constructor compartido con el camino
        # streaming. Antes esta lógica estaba duplicada y se desincronizó (la
        # compactación y el perfil de memoria solo existían aquí).
        from app.core import prompt_builder as pb

        parts = pb.PromptParts(message=pb.expand_slash(request.prompt))
        pb.add_skill(parts, request.prompt, skill_registry)
        await pb.handle_memory_commands(parts, request.prompt, memory_profile,
                                        memory_store, request.incognito)
        await pb.add_memory_async(parts, request.prompt, memory_profile,
                                  memory_store, request.incognito)
        pb.add_past_chats(parts, request.prompt, settings, request.conversation_history,
                          request.incognito)
        pb.add_documents(parts, request.prompt, rag_index, request.incognito)
        if not pb.add_project(parts, request):
            pb.add_workspace(parts, request.prompt, request.incognito)
        # Búsqueda web y lectura de URLs. Este es el camino que usa la app de
        # ESCRITORIO, y aquí no existía: en macOS/Windows nunca se buscaba en
        # internet por mucho que se mejorase el buscador.
        _web_used = await pb.add_web_context(
            parts, prompt=request.prompt, settings=settings,
            incognito=request.incognito, web_search=request.web_search,
            history=request.conversation_history,
            model=getattr(request, "force_model", None) or "",
        )
        await pb.add_history(
            parts, request.conversation_history, request.context_window,
            ollama_url=getattr(settings, "ollama_base_url", "") or "",
            model=getattr(registry, "orchestrator_model", "") or "",
        )
        effective_prompt = parts.render()

        # ── PASO 5: Seleccionar especialistas para este request ───────────────
        from app.editions import orchestration_enabled
        _multi = orchestration_enabled()   # Pro=True · Lite=False

        if not _multi and not request.specialists:
            # ANDROMEDA LITE — una sola IA (generalista) con power-scaling lineal.
            base_spec = registry.get_by_id("generalist") if registry.is_configured("generalist") else None
            if base_spec is None and active_specialists:
                base_spec = active_specialists[0]

            _lite_reason = "Andromeda Lite: una IA con power-scaling lineal"
            if base_spec is not None and not (request.force_model or "").strip():
                # El orquestador lineal estima la complejidad del prompt y elige el
                # nivel de potencia (low/mid/high/ultra), acotado por hardware y por
                # los modelos realmente disponibles para el generalista.
                import copy as _copy
                from app.core.linear_orchestrator import decide_power, LEVELS as _LV
                base_spec = _copy.copy(base_spec)
                _tiers = registry._tiers.get(base_spec.id)
                _avail = set()
                if _tiers:
                    for _lv in _LV:
                        _o = getattr(_tiers, _lv, None)
                        if _o and getattr(_o, "model_name", None):
                            _avail.add(_lv)
                _levels = (request.specialist_levels or {})
                _choice = _levels.get(base_spec.id) or _levels.get("generalist") or "auto"
                _t2l = {1: "low", 2: "mid", 3: "high", 4: "ultra"}
                _hw_max = _t2l.get(getattr(hardware, "max_tier", 4), "ultra")
                _dec = decide_power(request.prompt or "", user_choice=_choice,
                                    hardware_max_level=_hw_max, available_levels=_avail or None)
                _lvl_obj = getattr(_tiers, _dec.level, None) if _tiers else None
                if _lvl_obj and getattr(_lvl_obj, "model_name", None):
                    # El power-scaling manda: el modelo del nivel decidido (auto o
                    # elegido por el usuario) es el que se sirve. El modelo que el
                    # usuario activó en "Modelos de IA" ya ancla la auto-asignación
                    # de niveles, así que su preferencia está representada.
                    base_spec.model_name = _lvl_obj.model_name
                else:
                    # Sin modelo de nivel resuelto → respaldo: el override que el
                    # usuario activó en "Modelos de IA" (si existe).
                    try:
                        _ov = registry.get_model_override(base_spec.id)
                        if _ov:
                            base_spec.model_name = _ov
                    except Exception:
                        pass
                # GARANTÍA: el modelo final debe estar DESCARGADO en Ollama. Si
                # el del nivel/override no está, _pick_available cae a uno que sí
                # esté (evita el error "modelo no encontrado, ollama pull ...").
                try:
                    base_spec.model_name = registry._pick_available(base_spec.model_name, None)
                except Exception:
                    pass
                _lite_reason = f"Andromeda Lite · {_dec.reason}"
                logger.info(f"Lite linear (no-stream): nivel '{_dec.level}' "
                            f"(score={_dec.score}) → {base_spec.model_name}")

            selected_specialists = [base_spec] if base_spec else []
            classifier_result = {
                "specialists": [s.id for s in selected_specialists],
                "strategy": "single",
                "confidence": 1.0,
                "reasoning": _lite_reason,
                "source": "lite-linear",
            }
        # Si el usuario forzó especialistas → usarlos (validando que existen)
        elif request.specialists:
            selected_specialists = [
                registry.get_by_id(sid)
                for sid in request.specialists
                if registry.is_configured(sid)
            ]
            classifier_result = {
                "specialists": [s.id for s in selected_specialists],
                "strategy": request.strategy if request.strategy != "auto" else runtime_policy.effective_strategy,
                "confidence": 1.0,
                "reasoning": "Especialistas forzados por el usuario",
                "source": "forced",
            }
        else:
            # ── PASO 5b: Clasificar intención del prompt (solo Pro) ─────────
            from app.core.classifier import classify_prompt
            classifier_result = await classify_prompt(
                prompt=request.prompt,
                available_specialists=active_specialists,
                hardware_policy=base_policy,
                ollama_url=settings.ollama_base_url,
                orchestrator_model=registry.orchestrator_model,
                orchestrator_active=registry.orchestrator_active,
            )

            # Obtener los perfiles de los especialistas seleccionados
            selected_specialists = []
            for spec_id in classifier_result["specialists"]:
                if registry.is_configured(spec_id):
                    selected_specialists.append(registry.get_by_id(spec_id))

            # Fallback: si el clasificador no seleccionó nada válido
            if not selected_specialists and active_specialists:
                selected_specialists = [active_specialists[0]]
                classifier_result["specialists"] = [selected_specialists[0].id]
                classifier_result["reasoning"] += " [Fallback: primer especialista activo]"

        tracer.add_event(request_id, "classifier_result", {
            "source": classifier_result.get("source"),
            "confidence": classifier_result.get("confidence"),
            "specialists": classifier_result.get("specialists"),
            "strategy": classifier_result.get("strategy"),
        })

        # ── PASO 6: Determinar estrategia efectiva ────────────────────────────
        # La estrategia viene del clasificador, pero el PolicyEngine puede haberla
        # modificado durante la degradación
        effective_strategy = runtime_policy.effective_strategy
        if effective_strategy == "auto" or request.strategy == "auto":
            effective_strategy = classifier_result.get("strategy", "single")

        # Aplicar límite de paralelismo de la policy
        selected_specialists = selected_specialists[:runtime_policy.effective_parallel]

        logger.info(
            f"[{request_id[:8]}] "
            f"Especialistas: {[s.id for s in selected_specialists]} | "
            f"Estrategia: {effective_strategy} | "
            f"Fuente: {classifier_result.get('source')} | "
            f"Tier: T{runtime_policy.hardware_tier}"
        )

        # ── PASO 7: Ejecutar especialistas ────────────────────────────────────
        exec_config = {
            "ollama_url": settings.ollama_base_url,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": settings.ollama_timeout_seconds,
            # En incógnito no se ofrecen herramientas: fetch saldría a internet.
            "user_prompt": request.prompt,
            "mcp_manager": (None if request.incognito or parts.meta.get("memory_command")
                            else mcp_manager),
            "metrics": metrics,
            "hardware": hardware,
        }

        t_first_token = time.perf_counter()  # TTFT aproximado (sin streaming real en F0)
        exec_config["images"] = list(request.images or [])

        # Lite (una sola IA): si el modelo del nivel elegido no arranca por carga
        # (out of memory, timeout, error del runtime), bajamos de nivel y
        # reintentamos en vez de devolver error. Construimos el mapa nivel→modelo
        # desde el registry para saber a qué bajar.
        if len(selected_specialists) == 1 and not (request.images or []):
            from app.core.executor import call_with_fallback
            spec = selected_specialists[0]
            tiers = registry._tiers.get(spec.id)
            models_by_level = {}
            if tiers:
                for _lv in ("low", "mid", "high", "ultra"):
                    _o = getattr(tiers, _lv, None)
                    if _o and getattr(_o, "model_name", None):
                        models_by_level[_lv] = _o.model_name
            # nivel actual = el del modelo que el plan dejó en el especialista
            _cur = "mid"
            for _lv, _m in models_by_level.items():
                if _m == spec.model_name:
                    _cur = _lv
                    break
            single = await call_with_fallback(
                spec, effective_prompt, exec_config,
                level=_cur, models_by_level=models_by_level or {_cur: spec.model_name},
            )
            specialist_responses = [single]
        else:
            specialist_responses = await execute_specialists(
                specialists=selected_specialists,
                prompt=effective_prompt,
                strategy=effective_strategy,
                config=exec_config,
            )
        ttft_ms = (time.perf_counter() - t_first_token) * 1000

        # Registrar span de cada especialista
        for resp in specialist_responses:
            tracer.add_child_span(
                request_id,
                f"specialist:{resp['specialist_id']}",
                resp["latency_ms"],
                {
                    "model": resp["model_name"],
                    "success": resp["success"],
                    "chars": len(resp.get("content", "")),
                },
            )

        # Verificar si todos fallaron
        successful_responses = [r for r in specialist_responses if r.get("success")]
        if not successful_responses:
            errors = [f"{r['specialist_id']}: {r.get('error')}" for r in specialist_responses]
            # Detectar el tipo de fallo para que la UI muestre un aviso útil
            # en vez de un volcado de error técnico.
            error_kind = None
            if any(r.get("ollama_offline") for r in specialist_responses):
                error_kind = "ollama_offline"
            elif any(r.get("model_missing") for r in specialist_responses):
                error_kind = "model_missing"
            # Si hay un error de tipo conocido, usar su mensaje limpio (no el agregado).
            if error_kind:
                clean = next(
                    (r.get("error") for r in specialist_responses
                     if r.get("ollama_offline") or r.get("model_missing")),
                    None,
                )
                error_msg = clean or "; ".join(errors)
            else:
                error_msg = f"Todos los especialistas fallaron: {'; '.join(errors)}"
            logger.error(error_msg)
            return _error_response(request_id, trace_id, error_msg, error_kind=error_kind)

        # ── PASO 8: Fusionar respuestas ───────────────────────────────────────
        t_merge_start = time.perf_counter()
        final_response = await merge_responses(
            responses=specialist_responses,
            strategy=effective_strategy,
            original_prompt=request.prompt,
            ollama_url=settings.ollama_base_url,
            orchestrator_model=registry.orchestrator_model,
            config=exec_config,
        )
        merge_duration = (time.perf_counter() - t_merge_start) * 1000

        tracer.add_child_span(
            request_id,
            f"merger:{effective_strategy}",
            merge_duration,
            {"strategy": effective_strategy},
        )

        # ── PASO 9: Calcular métricas finales ─────────────────────────────────
        total_latency_ms = (time.perf_counter() - t_start) * 1000
        specialists_used = [r["specialist_id"] for r in successful_responses]

        routing_reasoning = tracer.build_routing_reasoning(
            classifier_result=classifier_result,
            runtime_policy=runtime_policy,
            hardware_info=hardware,
        )

        # Completar el TraceRecord
        trace.strategy_effective = effective_strategy
        trace.specialists_used = specialists_used
        trace.degraded = runtime_policy.degraded
        trace.degradation_reason = runtime_policy.degradation_reason
        trace.latency_ms = round(total_latency_ms, 1)
        trace.ttft_ms = round(ttft_ms, 1)
        trace.hardware_tier = runtime_policy.hardware_tier
        trace.vram_free_gb = runtime_policy.vram_free_gb
        trace.policy_applied = runtime_policy.policy_name
        trace.classifier_source = classifier_result.get("source", "keywords")
        trace.classifier_confidence = classifier_result.get("confidence", 0.0)
        trace.routing_reasoning = routing_reasoning
        trace.success = True

        tracer.add_event(request_id, "request_complete", {
            "latency_ms": round(total_latency_ms, 1),
            "ttft_ms": round(ttft_ms, 1),
            "specialists": specialists_used,
            "strategy": effective_strategy,
        })

        logger.info(
            f"[{request_id[:8]}] ✅ Completado: "
            f"{total_latency_ms:.0f}ms | "
            f"estrategia={effective_strategy} | "
            f"especialistas={specialists_used}"
        )

        # Exponer la decisión del orquestador lineal (potencia y modelo real usado).
        # Usamos el modelo que de verdad respondió (specialist_responses), que ya
        # refleja cualquier fallback de nivel que haya ocurrido.
        _models_used = {}
        for _r in specialist_responses:
            if _r.get("model_name"):
                _models_used[_r.get("specialist_id", "?")] = _r["model_name"]
        _power_tier = None
        _power_reason = classifier_result.get("reasoning")
        if specialist_responses:
            _used_model = specialist_responses[0].get("model_name")
            _sid = specialist_responses[0].get("specialist_id")
            _tiers = registry._tiers.get(_sid) if _sid else None
            if _tiers and _used_model:
                for _ti, _lv in ((1, "low"), (2, "mid"), (3, "high"), (4, "ultra")):
                    _o = getattr(_tiers, _lv, None)
                    if _o and getattr(_o, "model_name", None) == _used_model:
                        _power_tier = _ti
                        break

        from app.core.output_filters import strip_date_echo
        final_response = strip_date_echo(final_response or "")

        # Acciones de archivo: en este camino (el de escritorio) no se ejecutaban
        # nunca, así que la creación de archivos no funcionaba en la app.
        from app.core.file_actions import run_for_response
        _file_actions = run_for_response(final_response, settings=settings,
                                         incognito=request.incognito,
                                         project_id=getattr(request, "project_id", None))

        return ChatResponse(
            request_id=request_id,
            file_actions=_file_actions or None,
            skill_used=parts.meta.get("skill_used"),
            rag_sources=parts.meta.get("rag_sources"),
            web_used=_web_used,
            response=final_response,
            specialists_used=specialists_used,
            strategy_used=effective_strategy,
            latency_ms=round(total_latency_ms, 1),
            ttft_ms=round(ttft_ms, 1),
            hardware_tier=runtime_policy.hardware_tier,
            policy_applied=runtime_policy.policy_name,
            degraded=runtime_policy.degraded,
            degradation_reason=runtime_policy.degradation_reason,
            trace_id=trace_id,
            power_tier=_power_tier,
            power_reason=_power_reason,
            models_used=_models_used or None,
        )

    except Exception as exc:
        # Captura cualquier error inesperado del pipeline
        total_latency_ms = (time.perf_counter() - t_start) * 1000
        error_msg = f"Error inesperado en el pipeline: {type(exc).__name__}: {str(exc)}"
        logger.error(error_msg, exc_info=True)

        trace.success = False
        trace.error = error_msg
        trace.latency_ms = round(total_latency_ms, 1)

        return _error_response(request_id, trace_id, error_msg)

    finally:
        # SIEMPRE persistir el trace — incluso si hubo error
        # El finally garantiza que esto siempre se ejecuta
        metrics.record(request_id, {
            "latency_ms": trace.latency_ms,
            "ttft_ms": trace.ttft_ms,
            "success": trace.success,
            "strategy": trace.strategy_effective,
            "specialists_used": trace.specialists_used,
            "hardware_tier": trace.hardware_tier,
            "degraded": trace.degraded,
            "timestamp": trace.timestamp,
        })
        await tracer.end_span(request_id, trace)

        # Finalizar run MLOps con métricas completas
        if mlops_tracker and mlops_run_id:
            mlops_tracker.log_metrics(mlops_run_id, {
                "latency_ms": trace.latency_ms,
                "ttft_ms": trace.ttft_ms,
                "success": 1.0 if trace.success else 0.0,
                "degraded": 1.0 if trace.degraded else 0.0,
            })
            mlops_tracker.end_run(mlops_run_id, success=trace.success)


def _error_response(request_id: str, trace_id: str, error_msg: str,
                    error_kind: str | None = None) -> ChatResponse:
    """
    Construye un ChatResponse de error con el mensaje descriptivo.
    Siempre retorna JSON válido — nunca HTML ni excepción cruda.
    """
    return ChatResponse(
        request_id=request_id,
        response=f"Error: {error_msg}",
        specialists_used=[],
        strategy_used="none",
        latency_ms=0.0,
        ttft_ms=0.0,
        hardware_tier=1,
        policy_applied="error",
        degraded=False,
        degradation_reason=None,
        trace_id=trace_id,
        error_kind=error_kind,
    )
