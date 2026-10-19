"""Auto-instalación de runtimes MCP: hacer que sea plug and play de verdad."""
import asyncio
import logging

logging.disable(logging.CRITICAL)


def test_detects_runtime_from_command():
    from app.mcp import runtime_installer as ri
    assert ri.runtime_for_command(["npx", "-y", "@x/server"]) == "node"
    assert ri.runtime_for_command(["uvx", "mcp-server-time"]) == "uv"
    assert ri.runtime_for_command(["python", "server.py"]) is None
    assert ri.runtime_for_command([]) is None


def test_search_path_includes_common_install_dirs(monkeypatch):
    """Una app empaquetada no ve el PATH del shell: hay que ampliarlo.

    search_path() solo añade las carpetas que existen; en un runner limpio
    ~/.local/bin no existe, así que se simula que todas existen.
    """
    import os
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(ri.os.path, "isdir", lambda p: True)
    path = ri.search_path()
    assert os.path.expanduser("~/.local/bin") in path
    assert os.path.expanduser("~/.cargo/bin") in path


def test_ensure_path_is_idempotent():
    import os
    from app.mcp import runtime_installer as ri
    ri.ensure_path_in_environ()
    first = os.environ["PATH"]
    ri.ensure_path_in_environ()
    assert os.environ["PATH"].startswith(first.split(os.pathsep)[0])


def test_install_skips_when_already_available(monkeypatch):
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(ri, "is_available", lambda rt: True)
    out = asyncio.run(ri.install_runtime("uv"))
    assert out["ok"] is True and out["manual"] is False


def test_node_requires_manual_install_with_instructions(monkeypatch):
    """Node toca el sistema: se pide permiso en vez de instalarlo a escondidas."""
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(ri, "is_available", lambda rt: False)
    out = asyncio.run(ri.install_runtime("node"))
    assert out["ok"] is False and out["manual"] is True
    assert "nodejs.org" in out["message"] or "install" in out["message"].lower()


def test_failed_uv_install_gives_actionable_message(monkeypatch):
    """Un error crudo de curl no ayuda: debe decir qué comando ejecutar."""
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(ri, "is_available", lambda rt: False)
    monkeypatch.setattr(ri, "which", lambda tool: None)

    async def fake_run(cmd, timeout=240.0):
        return False, "curl: (22) error 403"

    monkeypatch.setattr(ri, "_run", fake_run)
    out = asyncio.run(ri.install_runtime("uv"))
    assert out["ok"] is False
    assert "uv" in out["message"] and ("install" in out["message"] or "brew" in out["message"])


def test_unknown_runtime_is_rejected():
    from app.mcp import runtime_installer as ri
    out = asyncio.run(ri.install_runtime("cobol"))
    assert out["ok"] is False and out["manual"] is True


def test_install_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.post("/api/mcp/install-runtime/cobol").status_code == 400
        r = c.post("/api/mcp/install-runtime/uv")
        assert r.status_code == 200
        assert "installed" in r.json() and "available_now" in r.json()


def test_enable_reports_missing_runtime(tmp_path, monkeypatch):
    """Activar un servidor sin su runtime debe explicar qué falta, no fallar mudo."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    from app.mcp import runtime_installer as ri
    monkeypatch.setattr(ri, "is_available", lambda rt: False)

    async def no_install(rt):
        return {"ok": False, "message": "Instala Node.js desde https://nodejs.org",
                "manual": True}

    monkeypatch.setattr(ri, "install_runtime", no_install)
    with TestClient(create_app()) as c:
        r = c.put("/api/mcp/servers/google-calendar", json={"enabled": True})
        body = r.json()
        assert body["connected"] is False
        assert body.get("manual_install") is True
        assert "nodejs.org" in body["message"]
        c.put("/api/mcp/servers/google-calendar", json={"enabled": False})
