"""
__init__.py — Factory de la aplicación FastAPI de Andromeda.
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

try:
    import colorlog
except ImportError:
    colorlog = None
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, settings as _resolved_settings, _resolve_config_paths
from app.middleware import RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from app.hardware.detector import HardwareDetector
from app.hardware.policy import PolicyEngine
from app.memory.store import SemanticMemoryStore
from app.mlops.tracker import MLOpsTracker
from app.mcp.manager import MCPManager
from app.observability.metrics import MetricsCollector
from app.observability.store import TraceStore
from app.observability.tracer import AndromedalTracer
from app.routes import (
    chat,
    health,
    models,
    traces,
    mlops,
    mcp as mcp_routes,
    context as context_routes,
    adr as adr_routes,
    alerts as alerts_routes,
    memory as memory_routes,
    multimodal as multimodal_routes,
    sandbox as sandbox_routes,
    files as files_routes,
    lab as lab_routes,
    auth as auth_routes,
    edition as edition_routes,
)
from app.middleware_security import SecurityMiddleware, AuthGateMiddleware
from app.specialists.registry import SpecialistRegistry
from app.core.warmup import warmup_models


# ── Logging ────────────────────────────────────────────────────────────────────

def _configure_logging(level: int = logging.INFO) -> None:
    if colorlog is not None:
        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(levelname)-8s%(reset)s "
                "%(cyan)s%(name)s%(reset)s: %(message)s",
                log_colors={
                    "DEBUG": "white", "INFO": "green",
                    "WARNING": "yellow", "ERROR": "red", "CRITICAL": "bold_red",
                },
            )
        )
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    root = logging.getLogger("andromeda")
    if not root.handlers:   # no duplicar handlers en reload
        root.addHandler(handler)
    root.setLevel(level)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings — primera lectura de env vars / .env
    settings = Settings()
    # Resolver rutas de config para que funcionen en binario (.app/.exe) y Docker,
    # no solo cuando se arranca desde backend/ con uvicorn.
    _resolve_config_paths(settings)

    # Logging level según entorno
    log_level = logging.DEBUG if settings.environment == "development" else logging.INFO
    _configure_logging(log_level)
    logger = logging.getLogger("andromeda.startup")

    logger.info("=" * 60)
    logger.info(f"  Andromeda {app.version} arrancando...")
    logger.info("=" * 60)

    # 1. Hardware
    hardware = HardwareDetector().detect()
    app.state.hardware = hardware
    logger.info(
        f"  Hardware: T{hardware.max_tier} | "
        f"VRAM: {hardware.total_vram_gb:.1f}GB | "
        f"Accel: {hardware.acceleration}"
    )

    # 2. Policy Engine
    policy_engine = PolicyEngine(settings.hardware_policies_path)
    app.state.policy_engine = policy_engine
    policy = policy_engine.get_policy(hardware)
    app.state.policy = policy
    logger.info(f"  Política: T{policy.tier}, max_parallel={policy.max_parallel}")

    # 3. Specialists Registry
    # En el binario (.app/.exe), el specialists.yaml empaquetado es de SOLO
    # LECTURA y la ruta por defecto es relativa: las asignaciones de modelo no
    # persisten. Si hay una ruta escribible (carpeta de datos del usuario),
    # copiamos ahí el YAML la primera vez y trabajamos siempre con esa copia.
    _spec_path = settings.specialists_config_path
    _wpath = getattr(settings, "specialists_writable_path", "")
    if _wpath:
        import shutil
        try:
            wp = Path(_wpath)
            wp.parent.mkdir(parents=True, exist_ok=True)
            if not wp.exists():
                src = Path(settings.specialists_config_path)
                if src.exists():
                    shutil.copyfile(src, wp)
                    logger.info(f"  Specialists: copiado a ruta escribible {wp}")
            if wp.exists():
                _spec_path = str(wp)
        except Exception as exc:
            logger.warning(f"  Specialists: no se pudo preparar ruta escribible: {exc}")
    registry = SpecialistRegistry(_spec_path)
    app.state.registry = registry
    status = registry.get_status_summary()
    logger.info(f"  Registry: {status['active']}/{status['total']} activos")
    if status.get("pending", 0) > 0:
        logger.warning(f"  Pendientes: {status.get('pending_ids', [])}")

    # 4. Observabilidad
    store = TraceStore(settings.telemetry_db_path)
    await store.init()
    app.state.store  = store
    app.state.tracer = AndromedalTracer(store)
    app.state.metrics = MetricsCollector()

    # 5. MLOps
    mlflow_uri = settings.mlflow_tracking_uri if settings.mlflow_enabled else None
    app.state.mlops_tracker = MLOpsTracker(
        db_path=settings.mlops_db_path,
        mlflow_uri=mlflow_uri,
    )
    logger.info(
        f"  MLOps: db='{settings.mlops_db_path}' | "
        f"MLflow={'activo' if settings.mlflow_enabled else 'inactivo'}"
    )

    # 6. Settings ref (para los routes que la necesiten)
    app.state.settings = settings

    # 6b. Resolver la URL de Ollama que realmente funciona y sobrescribirla.
    #     Así todo el código (chat, classifier, warmup) usa la URL correcta.
    from app.ollama_resolver import resolve_ollama_url
    working_url = await resolve_ollama_url(settings.ollama_base_url)
    if working_url:
        settings.ollama_base_url = working_url
        logger.info(f"  Ollama: {working_url} ✓")
        # Detectar modelos descargados para el fallback inteligente
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(trust_env=False) as _c:
                _r = await _c.get(f"{working_url}/api/tags", timeout=5.0)
                if _r.status_code == 200:
                    _models = [m["name"] for m in _r.json().get("models", [])]
                    registry.set_available_models(_models)
        except Exception as _e:
            logger.warning(f"  No se pudieron detectar modelos de Ollama: {_e}")
    else:
        logger.warning("  Ollama: no encontrado (probadas varias URLs)")

    logger.info(f"  Listo en http://0.0.0.0:{settings.port}")

    # 7. Warmup modelos en background
    asyncio.create_task(warmup_models(
        registry=registry,
        ollama_url=settings.ollama_base_url,
        hardware_tier=hardware.max_tier,
        vram_free_gb=hardware.total_vram_gb * 0.8,
    ))

    # 8. MCP Manager
    # Aseguramos que ANDROMEDA_WORKSPACE esté en el entorno para que los servidores
    # MCP (filesystem, git, sqlite) apunten al mismo workspace que el resto de la app.
    try:
        from app.core.workspace import get_workspace_root
        ws = str(get_workspace_root())
        os.makedirs(ws, exist_ok=True)
        os.environ.setdefault("ANDROMEDA_WORKSPACE", ws)
        logger.info(f"  Workspace MCP: {os.environ['ANDROMEDA_WORKSPACE']}")
    except Exception as exc:
        logger.warning(f"  No se pudo fijar ANDROMEDA_WORKSPACE: {exc}")

    mcp_config = os.path.join(
        os.path.dirname(settings.specialists_config_path), "mcp_servers.yaml"
    )
    mcp_manager = MCPManager(config_path=mcp_config)
    app.state.mcp_manager = mcp_manager
    asyncio.create_task(mcp_manager.initialize())
    logger.info("  MCP: inicializando servidores en background...")

    # 9. Memoria semántica
    memory_db = settings.memory_db_path
    memory_store = SemanticMemoryStore(
        db_path=memory_db,
        ollama_url=settings.ollama_base_url,
    )
    app.state.memory_store = memory_store
    logger.info("  Memoria semántica: iniciada")

    # 9b. Perfil de memoria del usuario (bloque persistente que se inyecta en
    # los prompts y donde guardan tanto el usuario como el auto-extractor).
    # Sin esto, /api/memory/profile devolvía 503 y el auto-guardado no hacía nada.
    from app.memory.profile import MemoryProfile
    app.state.memory_profile = MemoryProfile(
        Path(memory_db).parent / "memory_profile.json"
    )
    logger.info("  Perfil de memoria: iniciado")

    # 9c. Framework de A/B testing (comparar modelos en producción)
    from app.mlops.ab_testing import ABTesting
    ab_path = Path(memory_db).parent / "ab_experiments.json"
    app.state.ab_testing = ABTesting(ab_path)
    logger.info("  A/B testing: iniciado")

    # 9d. Feedback de usuario (señal de calidad online 👍/👎)
    from app.mlops.feedback import FeedbackStore
    fb_path = Path(memory_db).parent / "feedback.json"
    app.state.feedback_store = FeedbackStore(fb_path)
    logger.info("  Feedback de usuario: iniciado")

    # 9e. Model Registry (versionado + promoción a producción)
    from app.mlops.registry import ModelRegistry
    reg_path = Path(memory_db).parent / "model_registry.json"
    app.state.model_registry = ModelRegistry(reg_path)
    logger.info("  Model Registry: iniciado")

    # 9f. Histórico de calidad (serie temporal + drift + SLO)
    from app.mlops.quality_history import QualityHistory
    qh_path = Path(memory_db).parent / "quality_history.json"
    app.state.quality_history = QualityHistory(qh_path)
    logger.info("  Histórico de calidad: iniciado")

    # Snapshot periódico de calidad (cada 5 min) mientras la app esté viva.
    async def _quality_snapshot_loop():
        import asyncio as _aio
        while True:
            try:
                await _aio.sleep(300)
                m = app.state.metrics.get_summary()
                fb = app.state.feedback_store.stats() if getattr(app.state, "feedback_store", None) else {}
                app.state.quality_history.snapshot(m, fb.get("satisfaction"))
            except _aio.CancelledError:
                break
            except Exception:
                pass
    app.state._quality_task = asyncio.create_task(_quality_snapshot_loop())

    # 10. Project context placeholder
    app.state.project_context = None

    logger.info(f"  Docs: http://0.0.0.0:{settings.port}/docs")
    logger.info("=" * 60)

    yield

    logger.info("Andromeda apagándose...")
    # Cancelar la tarea de snapshot de calidad y guardar una foto final.
    try:
        t = getattr(app.state, "_quality_task", None)
        if t:
            t.cancel()
        m = app.state.metrics.get_summary()
        fb = app.state.feedback_store.stats() if getattr(app.state, "feedback_store", None) else {}
        app.state.quality_history.snapshot(m, fb.get("satisfaction"))
    except Exception:
        pass


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Andromeda API",
        version=_resolved_settings.app_version,
        description="Enterprise AI Orchestration Platform — local-first, hardware-aware.",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(AuthGateMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:80",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security + rate limiting middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, enabled=True)

    # Latency header
    @app.middleware("http")
    async def add_latency_header(request, call_next):
        t = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Andromeda-Latency-Ms"] = (
            f"{(time.perf_counter() - t) * 1000:.1f}"
        )
        return response

    # Global error handler — siempre JSON
    @app.exception_handler(Exception)
    async def global_error_handler(request, exc):
        logging.getLogger("andromeda.error").error(f"Unhandled: {exc}", exc_info=True)
        env = getattr(
            getattr(request.app.state, "settings", None), "environment", "production"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "code": "INTERNAL_ERROR",
                "message": str(exc) if env == "development" else "Error interno",
            },
        )

    # Routers
    app.include_router(chat.router,                prefix="/api/chat",    tags=["Chat"])
    app.include_router(models.router,              prefix="/api/models",  tags=["Models"])
    app.include_router(health.router,              prefix="/api/health",  tags=["Health"])
    app.include_router(traces.router,              prefix="/api/traces",  tags=["Traces"])
    from app.editions import feature_enabled as _fe
    if _fe("mlops_local"):  # MLOps avanzado solo en Pro
        app.include_router(mlops.router,           prefix="/api/mlops",   tags=["MLOps"])
    app.include_router(mcp_routes.router,          prefix="/api/mcp",     tags=["MCP"])
    app.include_router(context_routes.router,      prefix="/api/context", tags=["Context"])
    app.include_router(adr_routes.router,          prefix="/api/adr",     tags=["ADR"])
    app.include_router(alerts_routes.router,       prefix="/api/alerts",  tags=["Alerts"])
    app.include_router(memory_routes.router,       prefix="/api/memory",  tags=["Memory"])
    app.include_router(multimodal_routes.router,   prefix="/api/vision",  tags=["Vision"])
    app.include_router(sandbox_routes.router,      prefix="/api/sandbox", tags=["Sandbox"])
    app.include_router(files_routes.router,        prefix="/api/files",   tags=["Files"])
    from app.routes import documents as documents_routes
    app.include_router(documents_routes.router,    prefix="/api/documents", tags=["Documents"])
    from app.routes import orchestra_eval as orchestra_eval_routes
    from app.editions import feature_enabled as _fe_orch
    if _fe_orch("orchestration_multi"):  # explicación del plan multi-IA: solo Pro
        app.include_router(orchestra_eval_routes.router, prefix="/api/orchestra", tags=["Orchestra"])
    from app.routes import settings_routes
    app.include_router(settings_routes.router,     prefix="/api/settings", tags=["Settings"])
    try:
        settings_routes.apply_saved_language()
    except Exception:
        pass

    from app.editions import feature_enabled as _fe_lab
    if _fe_lab("fine_tuning"):  # Laboratorio de fine-tuning solo en Pro
        app.include_router(lab_routes.router)  # lab.py ya lleva prefix="/api/lab"
    app.include_router(auth_routes.router)
    app.include_router(edition_routes.router,      prefix="/api/edition", tags=["Edition"])
    from app.routes import cloud_routes
    app.include_router(cloud_routes.router)  # ya lleva prefix="/api/cloud"
    from app.routes import updates as updates_routes
    app.include_router(updates_routes.router)  # ya lleva prefix="/api/updates"
    from app.routes import backup as backup_routes
    app.include_router(backup_routes.router)  # ya lleva prefix="/api/backup"
    from app.routes import uistate as uistate_routes
    app.include_router(uistate_routes.router)  # ya lleva prefix="/api/uistate"
    from app.routes import ab as ab_routes
    app.include_router(ab_routes.router, prefix="/api/ab", tags=["AB-Testing"])
    from app.routes import feedback as feedback_routes
    app.include_router(feedback_routes.router, prefix="/api/feedback", tags=["Feedback"])
    from app.routes import registry as registry_routes
    app.include_router(registry_routes.router, prefix="/api/registry", tags=["Model-Registry"])

    # ── Endpoint /metrics para Prometheus (texto de exposición estándar) ──────
    from fastapi.responses import PlainTextResponse

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        """Métricas en formato Prometheus. Lo scrapea un servidor Prometheus y
        Grafana las visualiza. Ver deploy/monitoring/."""
        from app.observability.prometheus import render_metrics
        try:
            summary = app.state.metrics.get_summary()
            tools = app.state.metrics.get_tool_summary()
        except Exception:
            summary, tools = {"total_requests": 0}, {}
        ab = None
        try:
            ab = app.state.ab_testing.export_metrics()
        except Exception:
            pass
        _ver = ""
        try:
            _ver = getattr(app.state.settings, "app_version", "") or getattr(app.state.settings, "version", "") or app.version or ""
        except Exception:
            pass
        return PlainTextResponse(render_metrics(summary, tools, ab, version=_ver))

    # Servir el frontend SolidJS compilado (para el modo app de escritorio)
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        _base = os.path.dirname(_sys.executable)
    else:
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _frontend_dist = os.environ.get(
        'ANDROMEDA_FRONTEND_DIST',
        os.path.join(_base, 'frontend_dist')
    )
    if os.path.isdir(_frontend_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, 'assets')), name="assets")

        @app.get("/", include_in_schema=False)
        async def serve_spa():
            return FileResponse(os.path.join(_frontend_dist, 'index.html'))

        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa_catch_all(path: str):
            # API routes are handled before this catch-all
            file_path = os.path.join(_frontend_dist, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(_frontend_dist, 'index.html'))
    else:
        @app.get("/", tags=["Root"])
        async def root():
            return {"name": "Andromeda API", "version": _resolved_settings.app_version, "docs": "/docs"}

    return app
