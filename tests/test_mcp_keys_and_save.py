"""Claves de API de MCP y guardado de archivos en disco."""
import logging

logging.disable(logging.CRITICAL)


# ── Almacén de claves MCP ───────────────────────────────────────────────────

def test_secrets_store_roundtrip(tmp_path, monkeypatch):
    import os
    from app.mcp import secrets_store
    monkeypatch.delenv("TEST_MCP_KEY", raising=False)
    secrets_store.init(tmp_path)
    assert secrets_store.has_key("TEST_MCP_KEY") is False
    secrets_store.set_key("TEST_MCP_KEY", "valor-secreto")
    assert os.environ["TEST_MCP_KEY"] == "valor-secreto"   # aplicada sin reiniciar
    assert secrets_store.list_configured() == ["TEST_MCP_KEY"]
    assert secrets_store.delete_key("TEST_MCP_KEY") is True
    assert "TEST_MCP_KEY" not in os.environ


def test_secrets_persist_across_restart(tmp_path, monkeypatch):
    """El objetivo del almacén: sobrevivir al cierre de la app."""
    import os
    from app.mcp import secrets_store
    monkeypatch.delenv("PERSIST_KEY", raising=False)
    secrets_store.init(tmp_path)
    secrets_store.set_key("PERSIST_KEY", "abc123")
    del os.environ["PERSIST_KEY"]                          # simula reinicio
    assert secrets_store.init(tmp_path) >= 1
    assert os.environ.get("PERSIST_KEY") == "abc123"


def test_env_var_takes_priority_over_stored(tmp_path, monkeypatch):
    from app.mcp import secrets_store
    secrets_store.init(tmp_path)
    secrets_store.set_key("PRIO_KEY", "guardada")
    monkeypatch.setenv("PRIO_KEY", "exportada")
    secrets_store.init(tmp_path)
    import os
    assert os.environ["PRIO_KEY"] == "exportada"


def test_mcp_keys_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.put("/api/mcp/keys/MY_KEY", json={"value": "k-1"}).json()["saved"]
        assert "MY_KEY" in c.get("/api/mcp/keys").json()["configured"]
        # el estado se refleja en el listado de servidores, sin exponer valores
        body = c.get("/api/mcp/servers").json()
        assert all("keys_status" in s for s in body["servers"])
        assert "k-1" not in str(body)
        assert c.put("/api/mcp/keys/MY_KEY", json={"value": "  "}).status_code == 400
        assert c.delete("/api/mcp/keys/MY_KEY").json()["deleted"] is True


# ── Guardado de archivos ────────────────────────────────────────────────────

def test_save_file_writes_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    from pathlib import Path
    with TestClient(create_app()) as c:
        r = c.post("/api/save-file", json={"filename": "nota.md", "content": "# Hola"})
        assert r.status_code == 200 and r.json()["saved"]
        assert Path(r.json()["path"]).read_text(encoding="utf-8") == "# Hola"


def test_save_file_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        c.post("/api/save-file", json={"filename": "dup.txt", "content": "primero"})
        r = c.post("/api/save-file", json={"filename": "dup.txt", "content": "segundo"})
        assert r.json()["name"] == "dup-1.txt"


def test_save_file_blocks_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.post("/api/save-file", json={"filename": "../../../etc/passwd", "content": "x"})
        assert ".." not in r.json()["path"]
        assert r.json()["name"] == "passwd"


def test_save_file_rejects_empty_and_huge(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.post("/api/save-file", json={"filename": "a.txt", "content": ""}).status_code == 400
        big = "x" * (21 * 1024 * 1024)
        assert c.post("/api/save-file",
                      json={"filename": "big.txt", "content": big}).status_code == 413


def test_document_export_to_disk(tmp_path, monkeypatch):
    """Exportar a docx debe escribir el archivo, no devolver un stream."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    from pathlib import Path
    with TestClient(create_app()) as c:
        r = c.post("/api/documents/generate", json={
            "content": "# Titulo\n\nTexto", "format": "docx",
            "title": "Informe", "save_to_disk": True})
        assert r.status_code == 200 and r.json()["saved"]
        assert Path(r.json()["path"]).exists()


def test_feedback_endpoint_records(tmp_path, monkeypatch):
    """El feedback 👍/👎 debe persistir y reflejarse en las estadísticas."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        # Se mide el incremento: el almacén puede traer votos de otros tests.
        before = c.get("/api/feedback").json()
        assert c.post("/api/feedback",
                      json={"request_id": "r1", "positive": True}).json()["success"]
        c.post("/api/feedback", json={"request_id": "r2", "positive": False})
        after = c.get("/api/feedback").json()
        assert after["up"] == before["up"] + 1
        assert after["down"] == before["down"] + 1
        assert after["total"] == before["total"] + 2
