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

# ── Aislamiento de los datos de la suite ──────────────────────────────────
# Debe ocurrir ANTES de importar nada de la aplicación: varios módulos leen
# ANDROMEDA_DATA_DIR al importarse y su valor por defecto ("data") es una ruta
# RELATIVA, así que sin esto la suite escribe bases de datos y hasta un
# mcp_secrets.json dentro del propio repositorio, y contamina las ejecuciones
# siguientes (un documento indexado por un test hacía fallar a otro).
# Modo test: reduce los timeouts de sondeo de Ollama. Sin esto cada arranque de
# la aplicación espera a que fallen todas las URLs candidatas (~2,6 s) y, con
# más de 300 tests, eso son minutos de espera pura.
os.environ.setdefault("ANDROMEDA_ENVIRONMENT", "test")

if not os.environ.get("ANDROMEDA_TEST_DATA_DIR"):
    _test_data_dir = tempfile.mkdtemp(prefix="andromeda-tests-")
    os.environ["ANDROMEDA_TEST_DATA_DIR"] = _test_data_dir
    os.environ["ANDROMEDA_DATA_DIR"] = _test_data_dir

    # Fijar la variable no basta: algunos módulos caen a Path.home() y otros a
    # la ruta relativa "data", que apunta al repositorio. Redirigir el home de
    # la suite cierra esa vía de escape de una vez, en lugar de ir parcheando
    # test por test (13 ficheros escribían en data/ antes de esto).
    from pathlib import Path as _Path
    _real_home = _Path.home
    _fake_home = _Path(_test_data_dir) / "home"
    _fake_home.mkdir(parents=True, exist_ok=True)
    _Path.home = staticmethod(lambda: _fake_home)
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


@pytest.fixture(autouse=True)
def _restore_mcp_config():
    """Devuelve config/mcp_servers.yaml a su estado original tras cada test.

    Los tests que activan un servidor MCP escriben en el fichero REAL del
    repositorio. Si uno falla a medias deja un `enabled: true` puesto, lo que
    hace fallar a otros tests según el orden de ejecución y, peor, deja el
    repositorio modificado.
    """
    from pathlib import Path
    cfg = Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"
    original = cfg.read_text(encoding="utf-8") if cfg.exists() else None
    yield
    if original is not None and cfg.read_text(encoding="utf-8") != original:
        cfg.write_text(original, encoding="utf-8")


@pytest.fixture(scope="session")
def shared_client():
    """Cliente compartido por toda la sesión, para tests que solo LEEN.

    Crear la aplicación cuesta ~2,6 s (arranca el lifespan completo) y se hacía
    27 veces, así que la suite tardaba más de dos minutos. Dos minutos es
    suficiente para dejar de ejecutarla antes de cada commit, que es justo
    cuando más sirve.

    Los tests que modifican estado deben seguir creando su propia aplicación
    con un directorio de datos propio: compartir estado entre ellos provoca
    fallos que dependen del orden de ejecución.
    """
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_ollama_cache():
    """Olvida el resultado cacheado de buscar Ollama entre tests.

    La caché evita re-sondear todas las URLs en cada petición (260 ms cuando
    Ollama está apagado), pero entre tests debe limpiarse: si no, un test que
    levanta un servidor falso no lo detecta porque queda el fallo del anterior.
    """
    try:
        from app.ollama_resolver import reset_cache
        reset_cache()
    except Exception:
        pass
    yield
