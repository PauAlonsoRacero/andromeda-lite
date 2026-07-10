"""
conftest.py — Fixtures compartidas para los tests de Andromeda.

El problema principal: FastAPI necesita ejecutar el lifespan (startup)
para que app.state quede inicializado. En tests usamos un mock completo
para no depender de Ollama ni de hardware real.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Aseguramos que el backend esté en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_fake_hardware():
    from app.models.schemas import HardwareInfo
    return HardwareInfo(
        os="Linux",
        cpu_model="Test CPU",
        cpu_cores=8,
        ram_total_gb=16.0,
        ram_available_gb=8.0,
        gpus=[],
        total_vram_gb=0.0,
        acceleration="cpu",
        max_tier=1,
    )


def make_fake_policy():
    from app.models.schemas import HardwarePolicy
    return HardwarePolicy(
        tier=1,
        max_parallel=1,
        recommended_quant="Q4_K_M",
        max_context_tokens=2048,
        strategy_budget="conservative",
        can_run_verifier=False,
        safe_vram_threshold_gb=2.0,
        eligible_strategies=["single", "hardware_aware_fallback"],
    )


def make_fake_registry():
    """Registry real cargado desde el YAML real del proyecto."""
    from app.specialists.registry import SpecialistRegistry
    config_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', 'specialists.yaml'
    )
    return SpecialistRegistry(config_path)


def make_fake_settings(tmp_path):
    from app.config import Settings
    return Settings(
        environment="test",
        port=8000,
        ollama_base_url="http://localhost:11434",
        frontend_url="http://localhost",
        max_parallel_specialists=1,
        telemetry_enabled=True,
        telemetry_db_path=str(tmp_path / "traces.db"),
        specialists_config_path=os.path.join(
            os.path.dirname(__file__), '..', 'config', 'specialists.yaml'
        ),
        hardware_policies_path=os.path.join(
            os.path.dirname(__file__), '..', 'config', 'hardware_policies.yaml'
        ),
        mlops_enabled=False,
        mlops_db_path=str(tmp_path / "mlops.db"),
    )


async def make_fake_tracer(db_path: str):
    """TraceStore real sobre SQLite temporal."""
    from app.observability.store import TraceStore
    store = TraceStore(db_path)
    await store.init()
    return store


def make_fake_metrics():
    from app.observability.metrics import MetricsCollector
    return MetricsCollector()


def make_fake_mlops_tracker(db_path: str):
    from app.mlops.tracker import MLOpsTracker
    return MLOpsTracker(db_path=db_path, mlflow_uri=None)


def make_fake_policy_engine():
    from app.hardware.policy import PolicyEngine
    config_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', 'hardware_policies.yaml'
    )
    return PolicyEngine(config_path)


# ── Fixture principal ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def app_client():
    """
    Cliente HTTP con la app completamente inicializada en modo test.
    Todos los componentes son reales excepto Ollama (mockeado).
    """
    from app import create_app

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        application = create_app()

        # Inicializar todo el app.state manualmente (simula el lifespan)
        hardware    = make_fake_hardware()
        settings    = make_fake_settings(tmp_path)
        registry    = make_fake_registry()
        policy_eng  = make_fake_policy_engine()
        policy      = make_fake_policy()
        trace_store = await make_fake_tracer(str(tmp_path / "traces.db"))
        from app.observability.tracer import AndromedalTracer
        tracer      = AndromedalTracer(trace_store)
        metrics     = make_fake_metrics()
        mlops       = make_fake_mlops_tracker(str(tmp_path / "mlops.db"))

        application.state.hardware      = hardware
        application.state.settings      = settings
        application.state.registry      = registry
        application.state.policy_engine = policy_eng
        application.state.policy        = policy
        application.state.tracer        = tracer
        application.state.store         = trace_store  # TraceStore real (traces.py)
        application.state.metrics       = metrics
        application.state.mlops_tracker = mlops
        application.state.memory_store  = None   # sin memoria en tests
        application.state.mcp_manager   = None   # sin MCP en tests
        application.state.project_context = None

        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            yield client


@pytest.fixture
def app():
    """App sin estado inicializado — solo para unit tests que no llaman a endpoints."""
    from app import create_app
    return create_app()
