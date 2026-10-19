"""Estado honesto al activar servidores MCP y seguridad de subprocesos."""
import logging
import sys

logging.disable(logging.CRITICAL)


def test_frozen_app_never_uses_own_executable(monkeypatch):
    """El bug de la ventana duplicada.

    Bajo PyInstaller `sys.executable` es el binario de Andromeda, no Python.
    Invocarlo con `-m pip` no instala nada: abre OTRA COPIA DE LA APP.
    """
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Andromeda.app/Contents/MacOS/Andromeda")
    monkeypatch.setattr(ri, "which", lambda tool: None)
    assert ri._real_python() is None          # prefiere no instalar a relanzarse


def test_frozen_app_finds_system_python(monkeypatch):
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(ri, "which", lambda tool: "/usr/bin/python3")
    assert ri._real_python() == "/usr/bin/python3"


def test_frozen_app_rejects_python_inside_bundle(monkeypatch):
    """Un 'python' que resuelva dentro del propio bundle tampoco vale."""
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(ri, "which",
                        lambda tool: "/Applications/Andromeda.app/Contents/MacOS/python3")
    assert ri._real_python() is None


def test_normal_run_uses_current_interpreter(monkeypatch):
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert ri._real_python() == sys.executable


def test_subprocess_env_drops_pyinstaller_vars(monkeypatch):
    """Heredar _MEIPASS hace que el hijo cargue las librerías del bundle."""
    import asyncio
    from app.mcp import runtime_installer as ri
    monkeypatch.setenv("_MEIPASS", "/tmp/_MEI123")
    monkeypatch.setenv("PYTHONHOME", "/bundle/python")
    import sys
    codigo = ("import os;print('[%s][%s]' % (os.environ.get('_MEIPASS', ''),"
              " os.environ.get('PYTHONHOME', '')))")
    ok, out = asyncio.run(ri._run([sys.executable, "-c", codigo]))
    assert ok and out.strip() == "[][]"


def test_failed_enable_does_not_stay_enabled(tmp_path, monkeypatch):
    """Activar y no conectar no puede dejar el servidor marcado como activo."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        # google-calendar requiere una clave que no está configurada: no puede conectar
        r = c.put("/api/mcp/servers/google-calendar", json={"enabled": True}).json()
        assert r["connected"] is False
        assert r["enabled"] is False, "quedó 'activado' sin estar conectado"
        listed = {s["id"]: s for s in c.get("/api/mcp/servers").json()["servers"]}
        assert listed["google-calendar"]["enabled"] is False


def test_successful_enable_reports_connected(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.put("/api/mcp/servers/git", json={"enabled": True}).json()
        if r["connected"]:                      # requiere uvx en el entorno
            assert r["enabled"] is True
            assert r["tool_count"] > 0
        c.put("/api/mcp/servers/git", json={"enabled": False})
