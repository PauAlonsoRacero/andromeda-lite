"""Cierre limpio de la aplicación y salud de las dependencias."""
import asyncio
import json
import logging
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


def test_manager_can_close_every_server():
    """Cada servidor MCP es un proceso hijo: sin cierre quedan huérfanos."""
    from app.mcp.manager import MCPManager
    m = MCPManager(config_path="config/mcp_servers.yaml")
    assert hasattr(m, "disconnect_all")
    assert asyncio.run(m.disconnect_all()) == 0        # sin conexiones, sin error


def test_disconnect_all_survives_a_broken_client():
    """Un cliente que falla al cerrarse no puede impedir cerrar los demás."""
    from app.mcp.manager import MCPManager

    class Roto:
        async def disconnect(self):
            raise RuntimeError("cliente roto")

    class Bueno:
        cerrado = False

        async def disconnect(self):
            Bueno.cerrado = True

    m = MCPManager(config_path="config/mcp_servers.yaml")
    m._clients = {"roto": Roto(), "bueno": Bueno()}
    asyncio.run(m.disconnect_all())
    assert Bueno.cerrado, "un cliente roto impidió cerrar el resto"
    assert m._clients == {}


def test_lifespan_closes_mcp_servers():
    import inspect
    import app
    src = inspect.getsource(app)
    assert "disconnect_all" in src, "el cierre de la app no libera los servidores MCP"


def test_frontend_has_no_known_vulnerabilities():
    """Una vulnerabilidad alta en axios pasó desapercibida hasta una revisión
    manual, porque el CI solo auditaba las dependencias de Python."""
    pkg = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert "axios" in pkg.get("dependencies", {})
    axios = lock.get("packages", {}).get("node_modules/axios", {})
    version = axios.get("version", "0.0.0")
    mayor, menor, *_ = (int(x) for x in version.split("."))
    # GHSA-42h9-826w-cgv3 (DoS por recursión en formDataToJSON)
    assert (mayor, menor) >= (1, 12), f"axios {version} es vulnerable"


def test_ci_audits_frontend_dependencies():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "npm audit" in ci, "el CI no audita las dependencias del frontend"


def test_data_paths_respect_the_data_dir(tmp_path, monkeypatch):
    """Eran rutas relativas: los datos acababan donde se lanzara el proceso."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    import importlib
    from app import config as cfg
    importlib.reload(cfg)
    s = cfg.Settings()
    assert str(tmp_path) in s.memory_db_path
    assert not s.memory_db_path.startswith("data/")
