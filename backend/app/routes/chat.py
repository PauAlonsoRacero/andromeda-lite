"""
chat.py — Endpoint principal de Andromeda.

Endpoints:
  POST /api/chat             → procesar un prompt (SSE streaming o JSON completo)
  GET  /api/chat/strategies  → lista de estrategias disponibles
  GET  /api/chat/history     → historial de últimas 50 peticiones
"""

from datetime import timezone
import httpx
import json
import uuid
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.core.router import process_request
from app.models.schemas import ChatRequest
from app.core.streaming import staircase_stream

logger = logging.getLogger("andromeda.routes.chat")

router = APIRouter()

# Descripción de las 7 estrategias para el endpoint /strategies
# Las 12 estrategias del documento ModularAI Orchestrator v3
STRATEGIES_INFO = [
    {
        "id": "single",
        "name": "01 · Single",
        "description": "Un especialista, latencia mínima, cero overhead.",
        "use_when": "Tareas simples directas, dominio obvio, respuesta directa esperada.",
        "min_tier": 1,
        "specialists_needed": 1,
        "latency_overhead": "0ms",
    },
    {
        "id": "synthesis",
        "name": "02 · Synthesis",
        "description": "El orquestador sintetiza lo mejor de cada especialista en una respuesta fluida.",
        "use_when": "Perspectivas complementarias, ensayos técnicos, nivel 3 multidisciplinar.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "+5-15s",
    },
    {
        "id": "vote",
        "name": "03 · Vote",
        "description": "Mayoría semántica: la respuesta más cercana al centroide de longitud gana.",
        "use_when": "Preguntas factuales verificables, verificación de información, respuestas binarias.",
        "min_tier": 1,
        "specialists_needed": 2,
        "latency_overhead": "0ms",
    },
    {
        "id": "chain",
        "name": "04 · Chain",
        "description": "Cada especialista mejora el trabajo del anterior en serie.",
        "use_when": "Pipelines secuenciales: escribir código → documentarlo → traducirlo.",
        "min_tier": 1,
        "specialists_needed": 2,
        "latency_overhead": "0ms (ya secuencial)",
    },
    {
        "id": "debate",
        "name": "05 · Debate",
        "description": "Los modelos se cuestionan mutuamente: respuesta → crítica → mejora.",
        "use_when": "Análisis crítico, revisión, diseño de sistemas, pros/contras.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "+15-30s",
    },
    {
        "id": "parallel_merge",
        "name": "06 · Parallel Merge",
        "description": "Cada especialista cubre su sección del documento en paralelo.",
        "use_when": "Informes técnicos multi-área, propuestas, documentación extensa.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "+5-10s",
    },
    {
        "id": "confidence_weight",
        "name": "07 · Confidence Weight",
        "description": "Ponderación por certeza declarada [CONF:XX] de cada especialista.",
        "use_when": "Especialistas con diferente nivel de conocimiento sobre el tema.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "0ms",
    },
    {
        "id": "speculative",
        "name": "08 · Speculative",
        "description": "Genera y verifica de forma independiente. Si hay errores, corrige.",
        "use_when": "Código en producción, datos médicos, cálculos financieros, alta consecuencia.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "0ms si correcto, +5s si corrige",
    },
    {
        "id": "iterative_refine",
        "name": "09 · Iterative Refine",
        "description": "El segundo especialista refina directamente (no critica: mejora).",
        "use_when": "Primera respuesta buena pero mejorable, textos que necesitan pulido.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "+10-20s",
    },
    {
        "id": "best_of_n",
        "name": "10 · Best of N",
        "description": "N respuestas independientes, el orquestador selecciona la mejor.",
        "use_when": "Calidad máxima prioritaria, generación creativa, prompts ambiguos.",
        "min_tier": 3,
        "specialists_needed": 3,
        "latency_overhead": "0ms (selección) o +10s (orquestador)",
    },
    {
        "id": "mixture_experts",
        "name": "11 · Mixture of Experts",
        "description": "Pesos dinámicos por dominio: extrae el fragmento óptimo de cada especialista.",
        "use_when": "Tareas que cruzan dominios solapados: código+seguridad, medicina+psicología.",
        "min_tier": 3,
        "specialists_needed": 2,
        "latency_overhead": "+5-10s",
    },
    {
        "id": "socratic",
        "name": "12 · Socratic",
        "description": "Diálogo pedagógico: concepto + analogía + pregunta de comprensión.",
        "use_when": "Aprendizaje, onboarding, explicaciones a no-expertos, tutoriales.",
        "min_tier": 2,
        "specialists_needed": 2,
        "latency_overhead": "+20-40s",
    },
]


@router.post("", response_model=None)
async def chat(request: Request):
    """
    Endpoint principal — procesa un prompt con el orquestador de Andromeda.

    Modos:
      - stream=true (default): retorna SSE con tokens token a token
      - stream=false: retorna JSON completo al finalizar

    Body (ChatRequest):
      prompt:      str     — texto del usuario (requerido)
      strategy:    str     — estrategia o "auto" (default: "auto")
      specialists: list    — forzar especialistas específicos (default: [])
      temperature: float   — temperatura de generación (default: 0.7)
      max_tokens:  int     — tokens máximos (default: 2048)
      stream:      bool    — streaming SSE (default: true)
    """
    # ── Parsear y validar el body ─────────────────────────────────────────────
    try:
        raw_body = await request.json()
        chat_request = ChatRequest(**raw_body)
    except (ValidationError, Exception) as exc:
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": f"Body inválido: {str(exc)}",
            },
        )

    # ── Extraer componentes del estado de la app ──────────────────────────────
    registry = request.app.state.registry
    hardware = request.app.state.hardware
    policy_engine = request.app.state.policy_engine
    tracer = request.app.state.tracer
    metrics = request.app.state.metrics
    settings = request.app.state.settings

    # ── Modo streaming SSE ────────────────────────────────────────────────────
    if chat_request.stream:
        async def event_stream():
            """
            Genera los chunks SSE usando staircase streaming real.
            Los tokens aparecen token a token desde Ollama — TTFT < 1s en T2.

            Para requests con degradación o sin especialistas activos,
            cae al proceso completo (process_request) y envía en un chunk.
            """
            import uuid as _uuid
            try:
                async for _c in _event_stream_inner(_uuid):
                    yield _c
            except Exception as fatal:
                logger.error(f"Error fatal en event_stream: {fatal}", exc_info=True)
                err = {
                    "chunk_id": str(_uuid.uuid4()),
                    "request_id": str(_uuid.uuid4()),
                    "content": f"⚠️ Error: {str(fatal)}",
                    "is_final": True,
                    "metadata": {"error": True},
                }
                yield f"data: {json.dumps(err)}\n\n"
                yield "data: [DONE]\n\n"

        async def _event_stream_inner(_uuid):
            # ── Comprobación previa: ¿Ollama está vivo? ──────────────────────
            try:
                from app.ollama_resolver import resolve_ollama_url
                _ourl = await resolve_ollama_url(settings.ollama_base_url)
                if _ourl:
                    settings.ollama_base_url = _ourl
                    if registry.should_refresh_tags():
                        async with httpx.AsyncClient(trust_env=False) as _mc:
                            _tags = await _mc.get(f"{_ourl}/api/tags", timeout=4.0)
                            if _tags.status_code == 200:
                                _live = [m["name"] for m in _tags.json().get("models", [])]
                                if _live:
                                    registry.set_available_models(_live)
                else:
                    err_chunk = {
                        "chunk_id": str(_uuid.uuid4()),
                        "request_id": str(_uuid.uuid4()),
                        "content": (
                            "⚠️ No se detecta Ollama en ejecución. "
                            "Abre Ollama (o ejecútalo con `ollama serve`) y vuelve a intentarlo. "
                            "Descarga: https://ollama.com/download"
                        ),
                        "is_final": True,
                        "metadata": {"error": True, "error_detail": "ollama_unreachable",
                                     "error_kind": "ollama_offline"},
                    }
                    yield f"data: {json.dumps(err_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
            except Exception as _e:
                logger.debug(f"Pre-chequeo de Ollama falló: {_e}")

            # Obtener especialistas activos para el tier actual
            active = registry.get_eligible_for_tier(hardware.max_tier)
            # Si no queda ninguna IA activa pero hay modelos instalados (p. ej. se pulsó
            # "Desactivar" en Modelos), se usa la general: en Lite hay una sola, y
            # desactivarla dejaba el chat inservible con un aviso engañoso
            # ("descarga un modelo" teniendo diez instalados).
            if not active:
                active = registry.fallback_specialists(hardware.max_tier)
            if not active:
                # Sin especialistas — enviar error descriptivo
                status = registry.get_status_summary()
                err_chunk = {
                    "chunk_id": str(_uuid.uuid4()),
                    "request_id": str(_uuid.uuid4()),
                    "content": (
                        f"⚠️ Sin especialistas activos. Descarga al menos un modelo "
                        f"desde la sección Modelos (ej: llama3.2:3b) y vuelve a intentarlo. "
                        f"Estado: {status['active']}/{status['total']} activos."
                    ),
                    "is_final": True,
                    "metadata": {"error": True, "error_kind": "model_missing"},
                }
                yield f"data: {json.dumps(err_chunk)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Derivar política runtime (VRAM actual)
            base_policy    = policy_engine.get_policy(hardware)
            runtime_policy = policy_engine.derive_runtime_policy(
                hardware=hardware,
                request=chat_request,
                available_specialists=active,
                base_policy=base_policy,
            )

            # ── Refrescar modelos descargados AHORA (no solo al arrancar) ─────
            # Si el usuario acaba de descargar un modelo, el registry debe verlo
            # para resolver bien y no dar "modelo no encontrado".
            try:
                from app.ollama_resolver import resolve_ollama_url
                _ourl = await resolve_ollama_url(settings.ollama_base_url)
                if _ourl:
                    settings.ollama_base_url = _ourl
                    if registry.should_refresh_tags():
                        async with httpx.AsyncClient(trust_env=False) as _mc:
                            _tags = await _mc.get(f"{_ourl}/api/tags", timeout=4.0)
                            if _tags.status_code == 200:
                                _live = [m["name"] for m in _tags.json().get("models", [])]
                                if _live:
                                    registry.set_available_models(_live)
                            active = registry.get_eligible_for_tier(hardware.max_tier)
                            if not active:
                                active = registry.fallback_specialists(hardware.max_tier)
            except Exception as _e:
                logger.debug(f"No se pudo refrescar modelos vivos: {_e}")

            # ── Clasificar (solo si el usuario no fijó especialistas) ─────────
            from app.core.classifier import classify_prompt
            from app.editions import orchestration_enabled
            _multi = orchestration_enabled()   # Pro=True · Lite=False
            classifier_result = None
            # Si el usuario fuerza un modelo concreto, no hace falta clasificar
            # (ni gastar una llamada al modelo orquestador): va directo.
            _forcing = bool(getattr(chat_request, "force_model", None) and
                            chat_request.force_model.strip())
            # En Lite (sin orquestación multi) tampoco se clasifica: una sola IA.
            if _multi and not chat_request.specialists and not _forcing:
                try:
                    classifier_result = await classify_prompt(
                        prompt=chat_request.prompt,
                        available_specialists=active,
                        hardware_policy=base_policy,
                        ollama_url=settings.ollama_base_url,
                        orchestrator_model=registry.orchestrator_model,
                        orchestrator_active=registry.orchestrator_active,
                    )
                except Exception as clf_exc:
                    logger.warning(f"Clasificador falló ({clf_exc}); fallback simple")
                    classifier_result = None

            # ── Plan de orquestación ──────────────────────────────────────────
            from app.core.orchestrator import build_plan, OrchestrationPlan

            _fm = (getattr(chat_request, "force_model", None) or "").strip()
            if not _multi and not _fm:
                # ANDROMEDA LITE — orquestación lineal de UNA sola IA.
                # Usamos el especialista generalista ("modelo Andromeda") y dejamos
                # que el power-scaling elija el nivel según hardware/prompt. Sin
                # clasificador multi ni fusión: strategy="single", n_parallel=1.
                import copy as _copy
                base = None
                for s in active:
                    if s.id == "generalist":
                        base = _copy.copy(s); break
                if base is None and active:
                    base = _copy.copy(active[0])
                if base is None:
                    raise RuntimeError("No hay especialistas activos (Lite necesita el generalista)")

                # Aplicar la POTENCIA según el orquestador lineal de Lite.
                # - Si el usuario fija un nivel (low/mid/high/ultra) → se respeta.
                # - Si es 'auto' → decide_power() estima la complejidad del prompt
                #   y elige el nivel, acotado por el hardware y los modelos que de
                #   verdad existen para cada nivel.
                from app.core.linear_orchestrator import decide_power, LEVELS as _LV
                _levels = getattr(chat_request, "specialist_levels", None) or {}
                _user_choice = (_levels.get(base.id) or _levels.get("generalist") or "auto")

                # Niveles que tienen un modelo asignado de verdad
                _tiers = registry._tiers.get(base.id)
                _avail = set()
                if _tiers:
                    for _lv in _LV:
                        _o = getattr(_tiers, _lv, None)
                        if _o and getattr(_o, "model_name", None):
                            _avail.add(_lv)

                # Tope por hardware (max_tier → nivel)
                _tier_to_lvl = {1: "low", 2: "mid", 3: "high", 4: "ultra"}
                _hw_max = _tier_to_lvl.get(getattr(hardware, "max_tier", 4), "ultra")

                _decision = decide_power(
                    getattr(chat_request, "prompt", "") or "",
                    user_choice=_user_choice,
                    hardware_max_level=_hw_max,
                    available_levels=_avail or None,
                )
                _chosen_level = _decision.level
                _tier_n = {"low": 1, "mid": 2, "high": 3, "ultra": 4}.get(_chosen_level)
                try:
                    lvl_obj = getattr(_tiers, _chosen_level, None) if _tiers else None
                    if lvl_obj and getattr(lvl_obj, "model_name", None):
                        base.model_name = lvl_obj.model_name
                    logger.info(f"Lite linear: nivel '{_chosen_level}' "
                                f"(score={_decision.score}, {_decision.reason}) → {base.model_name}")
                    # Visible en Diagnóstico: permite comprobar que la potencia
                    # automática funciona (qué nivel, con qué puntuación y por qué).
                    try:
                        from app.observability import diagnostics as _dg
                        _dg.log("power", f"potencia '{_chosen_level}' → {base.model_name}",
                                level="success",
                                modo="forzado" if _decision.forced else "automático",
                                puntuacion=_decision.score, motivo=_decision.reason,
                                niveles_con_modelo=sorted(_avail) or "ninguno")
                    except Exception:
                        pass
                except Exception as exc:
                    logger.warning(f"No se pudo aplicar el nivel '{_chosen_level}': {exc}")

                plan = OrchestrationPlan(
                    specialists=[base],
                    strategy="single",
                    n_parallel=1,
                    mode="fast",
                    use_output_ai=False,
                    output_model=None,
                    classifier_source="lite-linear",
                    reasoning=f"Andromeda Lite · {_decision.reason}",
                    confidence=1.0,
                    complexity=max(_decision.score, 0.0),
                    power_tier=_tier_n or (getattr(base, "tier", 4) or 4),
                    models_used=[getattr(base, "model_name", "") or ""],
                )
                logger.info("Andromeda Lite: plan lineal single-IA (generalist)")
            elif _fm:
                # MODELO FORZADO: no pasamos por build_plan (cuyo fallback podría
                # tocar/resolver otros modelos como el orquestador). Construimos
                # un plan mínimo de UNA sola IA con el modelo elegido, sobre el
                # perfil "generalist" para un reporte coherente.
                import copy as _copy
                base = None
                for s in active:
                    if s.id == "generalist":
                        base = _copy.copy(s); break
                if base is None and active:
                    base = _copy.copy(active[0])
                if base is None:
                    # no hay especialistas activos: error claro
                    raise RuntimeError("No hay especialistas activos para forzar el modelo")
                base.model_name = _fm
                try:
                    from app.observability import diagnostics as _dg
                    _dg.log("power", f"modelo forzado por el usuario: {_fm} (la potencia automática no se aplica)",
                            level="warn")
                except Exception:
                    pass
                plan = OrchestrationPlan(
                    specialists=[base],
                    strategy="single",
                    n_parallel=1,
                    mode="fast",
                    use_output_ai=False,
                    output_model=None,
                    classifier_source="forced",
                    reasoning=f"Modelo forzado por el usuario: {_fm}",
                    confidence=1.0,
                    complexity=0.0,
                    power_tier=4,
                    models_used=[_fm],
                )
                logger.info(f"Modelo forzado (plan directo): {_fm} → generalist")
            else:
                # Camino normal Pro: toda la decisión en build_plan.
                plan = build_plan(
                    chat_request=chat_request,
                    active_specialists=active,
                    classifier_result=classifier_result,
                    runtime_policy=runtime_policy,
                    registry=registry,
                    hardware=hardware,
                )
            selected       = plan.specialists
            strategy       = plan.strategy
            classifier_src = plan.classifier_source

            # ── Análisis de imágenes (visión) ─────────────────────────────────
            # Si el usuario adjuntó imágenes, un modelo de visión (llava) las
            # describe primero, y esa descripción se inyecta en el prompt para
            # que el resto del pipeline pueda razonar sobre su contenido.
            # Construcción del prompt con el constructor COMPARTIDO con el
            # camino no-streaming. Antes esta lógica estaba escrita aquí por
            # separado y se desincronizó: la compactación de contexto y el
            # perfil de memoria solo existían en el otro camino, de modo que en
            # streaming (el modo normal) no se aplicaban nunca.
            from app.core import prompt_builder as pb

            _parts = pb.PromptParts(message=pb.expand_slash(chat_request.prompt))
            pb.add_skill(_parts, chat_request.prompt,
                         getattr(request.app.state, "skill_registry", None))
            # Órdenes explícitas sobre la memoria ("borra la memoria", "olvida
            # que…"): se ejecutan antes de inyectarla, sin depender del modelo.
            await pb.handle_memory_commands(
                _parts, chat_request.prompt,
                getattr(request.app.state, "memory_profile", None),
                getattr(request.app.state, "memory_store", None),
                chat_request.incognito,
            )
            await pb.add_memory_async(
                _parts, chat_request.prompt,
                getattr(request.app.state, "memory_profile", None),
                getattr(request.app.state, "memory_store", None),
                chat_request.incognito,
            )
            pb.add_past_chats(_parts, chat_request.prompt, settings,
                              chat_request.conversation_history, chat_request.incognito)
            pb.add_documents(_parts, chat_request.prompt,
                             getattr(request.app.state, "rag_index", None),
                             chat_request.incognito)
            if not pb.add_project(_parts, chat_request):
                pb.add_workspace(_parts, chat_request.prompt, chat_request.incognito,
                                 has_images=bool(getattr(chat_request, "images", None)))

            # Compatibilidad con el resto de la función, que aún usa estos nombres.
            _rag_doc_ids = _parts.meta.get("rag_sources", [])
            _matched_skill = _parts.meta.get("skill_used")
            # (el prompt se ensambla una sola vez, más abajo, con todas las piezas)
            _images_directas = None
            if getattr(chat_request, "images", None):
                # Imágenes adjuntas. Si el modelo que va a responder ve imágenes,
                # las recibe directamente; si no, otro modelo las describe en el
                # idioma de la interfaz; si no hay ninguno, se avisa sin inventar.
                from app.core import vision as _vis
                from app.observability import diagnostics as _dg
                _modelo_chat = next((getattr(sp, "model_name", "") for sp in selected), "")
                if _vis.is_vision_model(_modelo_chat):
                    _images_directas = chat_request.images[:3]
                    _dg.log("vision", f"imagen enviada directamente a {_modelo_chat}",
                            level="success")
                else:
                    _vm = _vis.pick_vision_model(
                        list(getattr(registry, "available_models", []) or []))
                    if not _vm:
                        pb.add_notice(_parts, _vis.no_model_notice())
                        _dg.log("vision", "sin modelo de visión instalado", level="warn")
                    else:
                        try:
                            desc = await _vis.describe(chat_request.images,
                                                       settings.ollama_base_url, _vm)
                            if desc:
                                _parts.documents = (
                                    "IMAGEN ADJUNTA (descrita por un modelo de visión; responde "
                                    f"a la pregunta del usuario a partir de esto):\n\n{desc}"
                                    + (f"\n\n{_parts.documents}" if _parts.documents else ""))
                                _dg.log("vision", f"imagen descrita por {_vm}", detail=desc,
                                        level="success")
                        except Exception as _vexc:
                            logger.warning(f"Visión falló con {_vm}: {_vexc}")
                            _dg.log("vision", f"fallo describiendo con {_vm}",
                                    detail=str(_vexc), level="error")

            # ── Búsqueda web (solo si NO es incógnito) ────────────────────────
            # En incógnito: 100% local, nunca toca internet. Y solo si el toggle
            # "Permitir salida de red" está activo en Ajustes.
            # Fase visible: si va a buscar en internet, decirlo ANTES. La
            # búsqueda puede tardar varios segundos y sin esto el usuario solo
            # veía una espera muda.
            try:
                from app.core.flags import get_flag as _gfp
                from app.core.web_search import extract_urls as _eu, needs_web_search as _nws
                if (not chat_request.incognito and chat_request.web_search
                        and _gfp(settings, "andromeda_network_egress")
                        and (_nws(chat_request.prompt) or _eu(chat_request.prompt))):
                    yield "data: " + json.dumps({
                        "chunk_id": str(uuid.uuid4()), "specialist_id": "system",
                        "content": "", "is_final": False,
                        "metadata": {"phase": "searching"},
                    }) + "\n\n"
            except Exception:
                pass

            web_used = await pb.add_web_context(
                _parts, prompt=chat_request.prompt, settings=settings,
                incognito=chat_request.incognito,
                web_search=chat_request.web_search,
                history=chat_request.conversation_history,
                model=getattr(chat_request, "force_model", None) or "",
            )

            # Historial de conversación, compactado si no cabe en el contexto.
            # Esto SOLO existía en el camino no-streaming: en streaming (el modo
            # normal) las conversaciones largas se truncaban sin resumir y se
            # perdía lo hablado al principio.
            await pb.add_history(
                _parts, chat_request.conversation_history, chat_request.context_window,
                ollama_url=getattr(settings, "ollama_base_url", "") or "",
                model=getattr(registry, "orchestrator_model", "") or "",
            )

            # El prompt final se ensambla UNA vez, tras recoger todas las piezas.
            # Antes cada bloque sobrescribía la variable y tiraba el trabajo
            # anterior: una búsqueda web borraba la skill, el RAG y la memoria.
            effective_prompt = _parts.render()

            # Iniciar run MLOps
            request_id = str(_uuid.uuid4())
            mlops_run_id = None

            # A/B testing: si hay un experimento activo y el usuario no forzó un
            # modelo, asignamos la variante del experimento (por hash de request_id,
            # respetando pesos) y recordamos la asignación para registrar el
            # resultado al terminar. Así comparamos modelos en producción real.
            _ab_assignment = None
            try:
                _ab = getattr(request.app.state, "ab_testing", None)
                if _ab and not (_fm or "").strip():
                    _exp = _ab.active_experiment()
                    if _exp:
                        _vname, _vmodel = _ab.assign(_exp, request_id)
                        _fm = _vmodel
                        _ab_assignment = (_exp["id"], _vname)
            except Exception:
                pass

            # Model Registry: si no hay modelo forzado ni A/B activo y el flag
            # 'serve_production' está activo, servir el modelo PROMOVIDO a producción.
            # Cierra el bucle MLOps: evaluar → registrar → promover → SERVIR.
            try:
                if not (_fm or "").strip() and not _ab_assignment:
                    from app.core.flags import get_flag as _gf2
                    if _gf2(settings, "andromeda_serve_production"):
                        _reg = getattr(request.app.state, "model_registry", None)
                        _prod = _reg.production_model() if _reg else None
                        if _prod:
                            _fm = _prod
                            logger.info(f"Sirviendo modelo de producción del registry: {_prod}")
            except Exception as _re:
                logger.warning(f"registry serve-production falló: {_re}")

            if request.app.state.mlops_tracker:
                mlops_run_id = request.app.state.mlops_tracker.start_run(
                    request_id=request_id,
                    # Incógnito: nunca escribir el texto del usuario en disco.
                    prompt_preview=("" if chat_request.incognito
                                    else chat_request.prompt[:100]),
                    strategy=strategy,
                    hardware_tier=hardware.max_tier,
                )

            try:
                # Config para streaming
                stream_config = {
                    "ollama_url":         settings.ollama_base_url,
                    "temperature":        chat_request.temperature,
                    "max_tokens":         chat_request.max_tokens,
                    "timeout":            settings.ollama_timeout_seconds,
                    "strategy":           runtime_policy.effective_strategy if strategy == "auto" else strategy,
                    "orchestrator_model": registry.orchestrator_model,
                    "mlops_tracker":      getattr(request.app.state, "mlops_tracker", None),
                    "hardware_tier":      hardware.max_tier,
                    # Datos completos del equipo: permiten ajustar contexto,
                    # hilos de CPU y capas en GPU a lo que de verdad hay.
                    "hardware":           hardware,
                    "force_model":        _fm or None,
                    # Imágenes para un modelo de chat que ve por sí mismo.
                    "images":             _images_directas,
                    # Herramientas MCP. Antes el streaming no las tenía (en el
                    # navegador no funcionaban nunca). En incógnito no se pasan:
                    # una herramienta como fetch saldría a internet, justo lo
                    # que ese modo promete no hacer.
                    # Tampoco si el mensaje era una orden sobre la memoria: el
                    # modelo tiraba del conector MCP "memory", otro sistema.
                    "mcp_manager": (None if (chat_request.incognito
                                             or _parts.meta.get("memory_command"))
                                    else getattr(request.app.state, "mcp_manager", None)),
                    "metrics":            getattr(request.app.state, "metrics", None),
                    "user_prompt":        chat_request.prompt,
                    # Nivel elegido por la potencia (o None en Pro): decide si
                    # los modelos de razonamiento piensan antes de responder.
                    "power_level":        locals().get("_chosen_level"),
                }

                # Config de escalado por reintento (opt-in vía ANDROMEDA_ESCALATION).
                # Si está activo y la respuesta de 1 IA sale floja, reintenta en
                # el tier superior. Por defecto desactivado (dobla latencia al saltar).
                import os as _os
                _escalation = None
                if _os.getenv("ANDROMEDA_ESCALATION", "0") in ("1", "true", "True"):
                    vram_free = hardware.total_vram_gb * 0.8 if hardware.total_vram_gb else 999.0
                    _escalation = {
                        "enabled": True,
                        "power_tier": plan.power_tier,
                        "max_tier": hardware.max_tier,
                        "hardware_tier": hardware.max_tier,
                        "vram_free_gb": vram_free,
                        "registry": request.app.state.registry,
                    }

                # Staircase streaming real — tokens llegan token a token
                # Antes del primer token, emitimos una frase de espera acorde al
                # nivel de potencia. La UI la muestra mientras el modelo carga, sin
                # gastar tokens del modelo ni anunciar tecnicismos de nivel.
                try:
                    from app.core.linear_orchestrator import loading_phrase, LEVELS as _LV
                    _lvl_name = _LV[max(0, min(plan.power_tier - 1, 3))]
                    _phrase = loading_phrase(_lvl_name, prompt=chat_request.prompt)
                    _ph_chunk = {
                        "chunk_id": str(_uuid.uuid4()),
                        "request_id": request_id,
                        "content": "",
                        "is_final": False,
                        "metadata": {"placeholder": _phrase, "power_level": _lvl_name},
                    }
                    yield f"data: {json.dumps(_ph_chunk)}\n\n"
                except Exception:
                    pass  # el placeholder es cosmético; nunca debe romper el stream

                _response_acc = []
                async for chunk in staircase_stream(
                    specialists=selected,
                    prompt=effective_prompt,
                    config=stream_config,
                    request_id=request_id,
                    use_output_ai=plan.use_output_ai,
                    output_model=plan.output_model,
                    escalation=_escalation,
                ):
                    # Acumular texto visible para estimar la confianza al final
                    if not chunk.get("is_final") and chunk.get("content"):
                        _response_acc.append(chunk["content"])
                    # Añadir metadatos de hardware al chunk final
                    if chunk.get("is_final") and not chunk["metadata"].get("error"):
                        meta = chunk["metadata"]
                        meta["hardware_tier"]     = hardware.max_tier
                        meta["policy_applied"]    = runtime_policy.policy_name
                        meta["degraded"]          = runtime_policy.degraded
                        meta["degradation_reason"]= runtime_policy.degradation_reason
                        meta["classifier_source"] = classifier_src
                        meta["web_used"]          = web_used
                        meta["power_tier"]        = plan.power_tier
                        meta["complexity"]        = round(plan.complexity, 2)

                        # ── Acciones de archivo (file system access) ──────────
                        # Si la IA emitió bloques ```andromeda:write|mkdir|…,
                        # los ejecutamos sobre el workspace (borrado reversible)
                        # y adjuntamos el resumen a la metadata para que el
                        # frontend lo muestre. En incógnito no se tocan archivos.
                        from app.core.file_actions import run_for_response
                        _fa = run_for_response("".join(_response_acc), settings=settings,
                                               incognito=chat_request.incognito,
                                               project_id=chat_request.project_id)
                        if _fa:
                            meta["file_actions"] = _fa
                        # Confianza estimada de la respuesta (heurística barata)
                        try:
                            from app.core.confidence import estimate_confidence, should_escalate
                            _full = "".join(_response_acc)
                            conf = estimate_confidence(chat_request.prompt, _full)
                            meta["confidence"] = conf
                            meta["could_escalate"] = should_escalate(
                                conf, plan.power_tier, hardware.max_tier)
                        except Exception:
                            pass

                        specialists_used = meta.get("specialists_used", [])
                        latencies_by_spec = meta.get("latencies_by_spec", {})
                        lat_ms = meta.get("latency_ms", 0)
                        ttft = meta.get("ttft_ms", 0)

                        # 1) Collector en memoria → alimenta /api/traces/metrics (Actividad)
                        try:
                            metrics.record(request_id, {
                                "latency_ms":       lat_ms,
                                "ttft_ms":          ttft,
                                "success":          True,
                                "degraded":         runtime_policy.degraded,
                                "strategy":         meta.get("strategy_used", strategy),
                                "specialists_used": specialists_used,
                                "hardware_tier":    hardware.max_tier,
                            })
                        except Exception as _e:
                            logger.warning(f"metrics.record falló: {_e}")

                        # 1b) A/B testing: registrar el resultado en la variante asignada.
                        try:
                            if _ab_assignment:
                                request.app.state.ab_testing.record(
                                    _ab_assignment[0], _ab_assignment[1], True, lat_ms)
                                # Adjuntar al meta para que el frontend pueda enviar
                                # el feedback de calidad (👍/👎) a esta variante.
                                meta["ab_experiment"] = _ab_assignment[0]
                                meta["ab_variant"] = _ab_assignment[1]
                        except Exception as _abe:
                            logger.warning(f"ab.record falló: {_abe}")
                        # request_id en el meta → el feedback de usuario lo referencia.
                        meta["request_id"] = request_id
                        if _rag_doc_ids:
                            meta["rag_sources"] = _rag_doc_ids
                        if _matched_skill:
                            meta["skill_used"] = _matched_skill

                        # 2) Tracker MLOps SQLite → alimenta /api/mlops/* (MLOps)
                        if request.app.state.mlops_tracker and mlops_run_id:
                            tracker = request.app.state.mlops_tracker
                            tracker.log_metrics(mlops_run_id, {
                                "latency_ms": lat_ms,
                                "ttft_ms":    ttft,
                                "success":    1.0,
                                "degraded":   1.0 if runtime_policy.degraded else 0.0,
                                # Params para MLflow (qué modelo/estrategia sirvió este run):
                                "model":      _fm or (selected[0].model_name if selected else "auto"),
                                "strategy":   meta.get("strategy_used", strategy),
                                "hardware_tier": hardware.max_tier,
                            })
                            tracker.log_specialists(mlops_run_id, specialists_used, latencies_by_spec)
                            # Registrar cada modelo usado para la vista "Modelos usados"
                            for sid in specialists_used:
                                model_name = next((s.model_name for s in selected if s.id == sid), "unknown")
                                tracker.update_model_registry(
                                    specialist_id=sid,
                                    model_name=model_name,
                                    hardware_tier=hardware.max_tier,
                                    latency_ms=latencies_by_spec.get(sid, lat_ms),
                                    success=True,
                                )
                            tracker.end_run(mlops_run_id, success=True)

                        # 2b) Memoria automática y corpus de entrenamiento. Antes
                        #     esto no existía en streaming y la memoria no se
                        #     guardaba nunca en uso normal.
                        # En segundo plano: guardar un recuerdo puede llamar a
                        # Ollama para calcular embeddings (hasta 10 s), y eso
                        # retrasaba el final de CADA respuesta que el usuario
                        # veía. La respuesta ya está completa; esto no la afecta.
                        _spawn_background(_after_response(
                            request, chat_request,
                            response_text="".join(_response_acc),
                            request_id=request_id,
                            model=next((s.model_name for s in selected
                                        if s.id in specialists_used), ""),
                        ))

                        # 3) Trace en SQLite → alimenta /api/traces (Actividad reciente).
                        #    Sin esto, la pantalla de Actividad queda siempre vacía.
                        try:
                            store = getattr(request.app.state, "store", None)
                            if store is not None:
                                from app.models.schemas import TraceRecord
                                await store.save(TraceRecord(
                                    request_id=request_id,
                                    prompt_preview=("" if chat_request.incognito
                                                    else (chat_request.prompt or "")[:100]),
                                    strategy=chat_request.strategy or "auto",
                                    strategy_effective=meta.get("strategy_used", strategy),
                                    specialists_used=specialists_used,
                                    degraded=runtime_policy.degraded,
                                    degradation_reason=runtime_policy.degradation_reason or "",
                                    latency_ms=lat_ms,
                                    ttft_ms=ttft or 0,
                                    hardware_tier=hardware.max_tier,
                                    policy_applied=runtime_policy.policy_name,
                                    classifier_source=meta.get("classifier_source", classifier_src),
                                    success=True,
                                ))
                        except Exception as _te:
                            logger.warning(f"No se pudo guardar el trace: {_te}")
                    yield f"data: {json.dumps(chunk)}\n\n"

            except Exception as exc:
                logger.error(f"Error en staircase stream: {exc}", exc_info=True)
                if request.app.state.mlops_tracker and mlops_run_id:
                    request.app.state.mlops_tracker.end_run(mlops_run_id, success=False)
                err_chunk = {
                    "chunk_id": str(_uuid.uuid4()),
                    "request_id": request_id,
                    "content": f"\n\n⚠️ Error interno: {str(exc)}",
                    "is_final": True,
                    "metadata": {"error": True},
                }
                yield f"data: {json.dumps(err_chunk)}\n\n"

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",    # Desactivar buffering en nginx
            },
        )

    # ── Modo JSON completo (stream=false) ─────────────────────────────────────
    try:
        # Asegurar que el registry sabe qué modelos están descargados, para que
        # el fallback elija uno disponible si el configurado no existe.
        try:
            from app.ollama_resolver import resolve_ollama_url
            _url = await resolve_ollama_url(settings.ollama_base_url)
            if _url:
                async with httpx.AsyncClient(trust_env=False) as _c:
                    _r = await _c.get(f"{_url}/api/tags", timeout=5.0)
                    if _r.status_code == 200:
                        _live = [m["name"] for m in _r.json().get("models", [])]
                        if _live:
                            registry.set_available_models(_live)
        except Exception:
            pass
        response = await process_request(
            request=chat_request,
            registry=registry,
            hardware=hardware,
            policy_engine=policy_engine,
            tracer=tracer,
            metrics=metrics,
            settings=settings,
            mlops_tracker=request.app.state.mlops_tracker,
            memory_store=getattr(request.app.state, 'memory_store', None),
            mcp_manager=getattr(request.app.state, 'mcp_manager', None),
            memory_profile=getattr(request.app.state, 'memory_profile', None),
            rag_index=getattr(request.app.state, 'rag_index', None),
            skill_registry=getattr(request.app.state, 'skill_registry', None),
        )

        # Efectos posteriores a la respuesta (memoria, corpus de entrenamiento),
        # compartidos con el camino streaming.
        # En segundo plano: la respuesta no debe esperar a que se calculen los
        # embeddings de la memoria (hasta 10 s con Ollama ocupado).
        _spawn_background(_after_response(
            request, chat_request,
            response_text=getattr(response, "response", "") or "",
            request_id=getattr(response, "request_id", "") or "",
            model=(getattr(response, "specialists_used", None) or [""])[0],
        ))

        return JSONResponse(content=response.model_dump())

    except Exception as exc:
        logger.error(f"Error procesando chat request: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "code": "INTERNAL_ERROR",
                "message": str(exc) if settings.environment == "development" else "Error interno",
            },
        )


# Referencias a las tareas en segundo plano: sin guardarlas, el recolector de
# basura puede destruir una tarea a medias (comportamiento documentado de asyncio).
_background_tasks: set = set()


def _spawn_background(coro) -> None:
    """Lanza una corrutina sin bloquear, registrando cualquier fallo."""
    import asyncio

    async def _seguro():
        try:
            await coro
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Tarea en segundo plano falló: {exc}")

    tarea = asyncio.create_task(_seguro())
    _background_tasks.add(tarea)
    tarea.add_done_callback(_background_tasks.discard)


async def _after_response(request: Request, chat_request, *, response_text: str,
                          request_id: str, model: str = "") -> None:
    """Lo que ocurre DESPUÉS de responder, idéntico en los dos caminos.

    Antes esto solo existía en el camino no-streaming. Como el streaming (el
    modo normal de la interfaz) retorna mucho antes, la extracción automática de
    memoria no se ejecutaba NUNCA en uso real: "recuerda que me llamo Pau" no se
    guardaba. Es el mismo tipo de fallo que tuvo la construcción del prompt, que
    también estaba duplicada y desincronizada.

    Nada de lo que hay aquí puede romper la respuesta: ya se ha enviado.
    """
    if chat_request.incognito:
        return
    settings = request.app.state.settings
    from app.core.flags import get_flag
    from app.observability import diagnostics as _dg

    # ── Memoria automática ────────────────────────────────────────────────
    _profile = getattr(request.app.state, "memory_profile", None)
    # Una orden sobre la memoria no es información sobre el usuario: al pedir
    # "elimina que me gusta el negro" se guardaba justo ese dato.
    from app.core.prompt_builder import is_memory_command
    if is_memory_command(chat_request.prompt or ""):
        _profile = None
    if _profile is not None and get_flag(settings, "andromeda_mem_autogenerate"):
        try:
            from app.memory.extractor import extract_memories
            nuevos = extract_memories(chat_request.prompt or "")
            from app.memory.structure import es_sensible
            if not get_flag(settings, "andromeda_mem_sensitive"):
                nuevos = [n for n in nuevos if not es_sensible(n[0])]
            for contenido, _categoria, topic in nuevos:
                frase = contenido.strip()
                if frase:
                    frase = frase[0].upper() + frase[1:]
                # Clave acumulable: los gustos, objetivos y notas se suman en
                # vez de reemplazarse (antes un gusto nuevo borraba el anterior).
                from app.memory.extractor import topic_key
                tkey = topic_key(topic, frase)
                _profile.upsert_fact(tkey, frase)

            # También al almacén semántico, para recuperar solo lo relevante.
            _store = getattr(request.app.state, "memory_store", None)
            if _store is not None:
                for contenido, categoria, _topic in nuevos:
                    try:
                        await _store.save(contenido, source="chat", category=categoria)
                    except Exception as _sexc:
                        logger.debug(f"No se pudo indexar el recuerdo: {_sexc}")
            _dg.log("memory", f"extracción: {len(nuevos)} datos guardados",
                    data={"datos": [n[0][:60] for n in nuevos]},
                    level="success" if nuevos else "info")
        except Exception as _exc:
            logger.warning(f"Extracción de memoria falló: {_exc}")
            _dg.log("memory", "fallo en la extracción", detail=str(_exc), level="error")

    # ── Corpus de entrenamiento (Apolo) ───────────────────────────────────
    _corpus = getattr(request.app.state, "training_corpus", None)
    if _corpus is not None:
        try:
            _corpus.record(
                request_id, chat_request.prompt or "", response_text,
                model=model or "",
                history=chat_request.conversation_history or [],
                incognito=chat_request.incognito,
            )
        except Exception as _exc:
            logger.debug(f"Corpus de entrenamiento: {_exc}")


@router.get("/strategies")
async def get_strategies(request: Request) -> JSONResponse:
    """
    Lista las 7 estrategias disponibles con descripción y cuándo usar cada una.
    Filtra por las elegibles en el tier de hardware actual.
    """
    hardware = request.app.state.hardware
    policy_engine = request.app.state.policy_engine
    policy = policy_engine.get_policy(hardware)

    strategies_with_availability = []
    for s in STRATEGIES_INFO:
        s_copy = s.copy()
        s_copy["available_in_current_tier"] = s["id"] in policy.eligible_strategies
        s_copy["current_tier"] = hardware.max_tier
        strategies_with_availability.append(s_copy)

    return JSONResponse(content={
        "strategies": strategies_with_availability,
        "current_tier": hardware.max_tier,
        "eligible_in_current_tier": policy.eligible_strategies,
    })


@router.get("/history")
async def get_history(
    request: Request,
    limit: int = 50,
) -> JSONResponse:
    """
    Historial de las últimas N peticiones.
    Alias de GET /api/traces con campos reducidos para la UI.
    """
    store = request.app.state.store
    if store is None or not hasattr(store, "get_recent"):
        return JSONResponse(content={"history": [], "count": 0})
    traces = await store.get_recent(limit=min(limit, 200))

    # Versión resumida para el historial de la UI
    history = [
        {
            "request_id": t.get("request_id"),
            "timestamp": t.get("timestamp"),
            "prompt_preview": t.get("prompt_preview"),
            "strategy": t.get("strategy_effective"),
            "specialists_used": t.get("specialists_used", []),
            "latency_ms": t.get("latency_ms"),
            "success": t.get("success"),
            "degraded": t.get("degraded"),
        }
        for t in traces
    ]

    return JSONResponse(content={"history": history, "count": len(history)})


@router.get("/history/search")
async def search_history(q: str, limit: int = 20, request: Request = None) -> JSONResponse:
    """
    Busca en el historial de conversaciones por texto.
    Busca en el prompt y en la respuesta del asistente.
    """
    tracer = request.app.state.tracer
    try:
        results = await tracer.search_traces(query=q, limit=limit)
        return JSONResponse(content={"results": results, "query": q, "count": len(results)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/prompts")
async def save_prompt(request: Request) -> JSONResponse:
    """Guarda un prompt en la biblioteca personal."""
    import sqlite3
    import datetime
    body = await request.json()
    title   = body.get("title", "")
    content = body.get("content", "")
    tags    = body.get("tags", [])
    if not content.strip():
        return JSONResponse(status_code=400, content={"error_key": "err.content_required"})

    db_path = request.app.state.settings.mlops_db_path
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_prompts (
            id        TEXT PRIMARY KEY,
            title     TEXT,
            content   TEXT NOT NULL,
            tags      TEXT DEFAULT '[]',
            created   TEXT NOT NULL,
            use_count INTEGER DEFAULT 0
        )
    """)
    pid = str(__import__("uuid").uuid4())
    conn.execute(
        "INSERT INTO saved_prompts VALUES (?,?,?,?,?,?)",
        (pid, title, content, __import__("json").dumps(tags), datetime.datetime.now(timezone.utc).isoformat(), 0)
    )
    conn.commit(); conn.close()
    return JSONResponse(content={"id": pid, "title": title, "success": True})


@router.get("/prompts")
async def get_prompts(request: Request) -> JSONResponse:
    """Lista todos los prompts guardados."""
    import sqlite3
    import json as _json
    db_path = request.app.state.settings.mlops_db_path
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_prompts (
                id TEXT PRIMARY KEY, title TEXT, content TEXT NOT NULL,
                tags TEXT DEFAULT '[]', created TEXT NOT NULL, use_count INTEGER DEFAULT 0
            )
        """)
        rows = conn.execute("SELECT * FROM saved_prompts ORDER BY use_count DESC, created DESC").fetchall()
        conn.close()
        prompts = [dict(r) for r in rows]
        for p in prompts:
            try: p["tags"] = _json.loads(p.get("tags", "[]"))
            except (ValueError, TypeError): p["tags"] = []
        return JSONResponse(content={"prompts": prompts, "count": len(prompts)})
    except Exception:
        return JSONResponse(content={"prompts": [], "count": 0})


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, request: Request) -> JSONResponse:
    import sqlite3
    db_path = request.app.state.settings.mlops_db_path
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM saved_prompts WHERE id=?", (prompt_id,))
    conn.commit(); conn.close()
    return JSONResponse(content={"success": True})


@router.post("/prompts/{prompt_id}/use")
async def use_prompt(prompt_id: str, request: Request) -> JSONResponse:
    """Incrementa el contador de uso de un prompt."""
    import sqlite3
    db_path = request.app.state.settings.mlops_db_path
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE saved_prompts SET use_count=use_count+1 WHERE id=?", (prompt_id,))
    conn.commit(); conn.close()
    return JSONResponse(content={"success": True})


# ── EVALUACIÓN AUTOMÁTICA DE RESPUESTAS ──────────────────────────────────────

@router.post("/evaluate")
async def evaluate_response(request: Request) -> JSONResponse:
    """
    Evalúa la calidad de una respuesta de IA usando otra IA como juez.
    Implementa el patrón LLM-as-Judge usado en investigación de modelos.

    Criterios evaluados:
      - Corrección técnica (0-10)
      - Completitud (0-10)
      - Claridad (0-10)
      - Relevancia al prompt (0-10)
      - Score global (promedio ponderado)

    Body: {"prompt": "...", "response": "...", "judge_model": "phi3.5:3.8b"}
    """
    import json as _json
    body     = await request.json()
    prompt   = body.get("prompt", "")
    response = body.get("response", "")
    judge    = body.get("judge_model") or request.app.state.registry.orchestrator_model
    settings = request.app.state.settings

    if not prompt or not response:
        return JSONResponse(status_code=400, content={"error_key": "err.prompt_response_required"})

    judge_prompt = f"""Evalúa la siguiente respuesta de IA según estos criterios.
Responde SOLO con un JSON válido, sin texto adicional.

PROMPT DEL USUARIO:
{prompt}

RESPUESTA DE LA IA:
{response}

Evalúa en escala 0-10:
{{
  "correctness": <0-10>,
  "completeness": <0-10>,
  "clarity": <0-10>,
  "relevance": <0-10>,
  "reasoning": "<explicación breve en español>",
  "suggestions": "<mejoras concretas>"
}}"""

    try:
        async with __import__("httpx").AsyncClient() as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model":   judge,
                    "messages":[{"role":"user","content":judge_prompt}],
                    "options": {"temperature":0.1,"num_predict":500},
                    "stream":  False,
                },
                timeout=30.0,
            )
            r.raise_for_status()
            content = r.json().get("message",{}).get("content","")
            # Limpiar y parsear JSON
            content = content.strip()
            if content.startswith("```"): content = content.split("\n",1)[1].rsplit("```",1)[0]
            scores = _json.loads(content)
            scores["global"] = round(
                (scores.get("correctness",5)*0.35 +
                 scores.get("completeness",5)*0.25 +
                 scores.get("clarity",5)*0.20 +
                 scores.get("relevance",5)*0.20), 1
            )
            scores["judge_model"] = judge
            return JSONResponse(content={"success":True,"evaluation":scores})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/benchmark")
async def run_benchmark(request: Request) -> JSONResponse:
    """
    Ejecuta un benchmark formal contra un golden dataset.
    Compara Andromeda (multi-IA) vs modelo único.

    Body: {"prompts": [...], "single_model": "mistral:7b", "runs": 3}
    """
    import time
    import httpx as _httpx
    body         = await request.json()
    prompts      = body.get("prompts", GOLDEN_DATASET)
    single_model = body.get("single_model", "mistral:7b")
    runs         = min(body.get("runs", 1), 3)
    settings     = request.app.state.settings

    results = []
    for p in prompts[:10]:  # Máximo 10 prompts por run
        entry = {"prompt": p, "single": [], "andromeda": []}
        for _ in range(runs):
            # Single model
            t0 = time.perf_counter()
            try:
                async with _httpx.AsyncClient(trust_env=False) as client:
                    r = await client.post(
                        f"{settings.ollama_base_url}/api/chat",
                        json={"model":single_model,"messages":[{"role":"user","content":p}],
                              "options":{"temperature":0.7,"num_predict":512},"stream":False},
                        timeout=60.0,
                    )
                    single_resp = r.json().get("message",{}).get("content","")
                    single_ms   = (time.perf_counter()-t0)*1000
                    entry["single"].append({"latency_ms":round(single_ms),"length":len(single_resp)})
            except Exception as e:
                entry["single"].append({"error":str(e)})

        results.append(entry)

    # Calcular estadísticas
    summary = {
        "prompts_tested":    len(results),
        "single_model":      single_model,
        "avg_single_latency": round(
            sum(r["single"][0].get("latency_ms",0) for r in results if r["single"]) / max(len(results),1)
        ),
    }
    return JSONResponse(content={"results": results, "summary": summary})


GOLDEN_DATASET = [
    "Explica qué es Docker y para qué sirve en 3 puntos",
    "¿Cuál es la diferencia entre un proceso y un thread?",
    "Escribe una función Python que calcule el factorial de forma recursiva",
    "¿Qué es asyncio en Python y cuándo usarlo?",
    "Explica el patrón Repository en arquitectura de software",
    "¿Qué es un índice en una base de datos y cómo mejora el rendimiento?",
    "Diferencia entre TCP y UDP",
    "¿Qué es CI/CD y cuáles son sus beneficios?",
    "Explica qué es una API REST y sus principios",
    "¿Cuándo usar PostgreSQL vs MongoDB?",
]
