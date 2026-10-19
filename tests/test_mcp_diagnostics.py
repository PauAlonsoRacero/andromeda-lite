"""Diagnóstico de conexión MCP: saber POR QUÉ falla un servidor."""
import asyncio
import logging

logging.disable(logging.CRITICAL)


def test_missing_binary_gives_actionable_error():
    """Si falta npx/uvx, el mensaje debe decir qué instalar, no un genérico."""
    from app.mcp.protocol import MCPStdioClient
    c = MCPStdioClient(server_id="x", command=["binario-que-no-existe-xyz"], env={})
    assert asyncio.run(c.connect()) is False
    assert "No se encontró" in c.last_error
    assert "Instala" in c.last_error


def test_client_starts_with_empty_error():
    from app.mcp.protocol import MCPStdioClient
    assert MCPStdioClient(server_id="x", command=["echo"], env={}).last_error == ""


def test_manager_records_reason_for_failure():
    """El manager debe conservar el motivo para exponerlo en la UI."""
    from app.mcp.manager import MCPManager
    m = MCPManager(config_path="config/mcp_servers.yaml")
    assert m.last_error("inexistente") == ""
    ok = asyncio.run(m._connect_server("falso", {"command": ["binario-inexistente-xyz"]}))
    assert ok is False
    assert "No se encontró" in m.last_error("falso")


def test_manager_reports_missing_keys_as_reason():
    """Si faltan claves, ese es el diagnóstico más útil y debe ir primero."""
    from app.mcp.manager import MCPManager
    m = MCPManager(config_path="config/mcp_servers.yaml")
    asyncio.run(m._connect_server("necesita-clave", {
        "command": ["binario-inexistente-xyz"],
        "requires_key": ["UNA_CLAVE_QUE_NO_EXISTE"],
    }))
    assert "UNA_CLAVE_QUE_NO_EXISTE" in m.last_error("necesita-clave")


def test_diagnose_endpoint_reports_runtimes(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        d = c.get("/api/mcp/diagnose").json()
        assert "node" in d["runtimes"] and "python-uv" in d["runtimes"]
        for rt in d["runtimes"].values():
            assert "available" in rt and "install_hint" in rt
        assert "errors" in d and "connected_servers" in d


def test_servers_endpoint_exposes_error_field(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        for s in c.get("/api/mcp/servers").json()["servers"]:
            assert "error" in s and "keys_status" in s
