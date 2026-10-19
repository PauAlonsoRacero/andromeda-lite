"""Casos límite encontrados ejercitando la app, no en los tests originales."""
import logging
import threading

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    # Hay que fijar AMBAS cosas: el directorio de datos y Path.home(). Varios
    # módulos usan "data" (ruta RELATIVA) como valor por defecto, así que si
    # solo se parchea una, la app acaba escribiendo dentro del repositorio.
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Nombres de archivo: devolvían 500 ───────────────────────────────────────

def test_very_long_filename_is_truncated(tmp_path, monkeypatch):
    """El sistema de ficheros corta en 255 bytes: antes esto daba error 500."""
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/save-file", json={"filename": "a" * 400 + ".md", "content": "x"})
        assert r.status_code == 200
        assert len(r.json()["name"].encode("utf-8")) <= 255
        assert r.json()["name"].endswith(".md")     # conserva la extensión


def test_accents_are_transliterated_not_mangled(tmp_path, monkeypatch):
    """'informe_año.md' debe seguir siendo legible, no 'informe_a-o.md'."""
    with _client(tmp_path, monkeypatch) as c:
        name = c.post("/api/save-file",
                      json={"filename": "informe_año.md", "content": "x"}).json()["name"]
        assert name == "informe_ano.md"


def test_degenerate_filenames_get_a_default(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        for bad in ("..", ".", "", "...", "///"):
            r = c.post("/api/save-file", json={"filename": bad, "content": "x"})
            assert r.status_code == 200
            assert r.json()["name"].startswith("andromeda")


def test_traversal_filename_keeps_only_basename(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/save-file", json={"filename": "../../etc/passwd", "content": "x"})
        assert r.json()["name"] == "passwd"
        assert ".." not in r.json()["path"]


# ── Concurrencia: el estado en disco no puede corromperse ──────────────────

def test_concurrent_writes_keep_state_consistent(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        errors = []

        def hammer(i):
            try:
                for j in range(8):
                    c.post("/api/rag/documents",
                           json={"id": f"d{i}-{j}", "text": f"contenido {j} " * 10})
                    c.post("/api/feedback", json={"request_id": f"r{i}{j}", "positive": True})
            except Exception as exc:                 # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=hammer, args=(i,)) for i in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, errors
        # el índice sigue siendo consultable y coherente
        assert c.get("/api/rag/stats").json()["documents"] >= 32


# ── Estado que debe sobrevivir a cerrar la app ─────────────────────────────

def test_everything_persists_across_restart(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app

    with TestClient(create_app()) as c1:
        c1.put("/api/memory/profile", json={"text": "Me llamo Pau."})
        c1.post("/api/rag/documents", json={"id": "p.md", "text": "dato persistente"})
        c1.post("/api/skills/user",
                json={"id": "mia", "name": "Mía", "description": "skill propia de prueba"})
        c1.put("/api/mcp/keys/PERSIST_TEST", json={"value": "secreto"})

    os.environ.pop("PERSIST_TEST", None)              # simula proceso nuevo
    with TestClient(create_app()) as c2:
        assert "Pau" in c2.get("/api/memory/profile").json()["manual"]
        assert "p.md" in {d["id"] for d in c2.get("/api/rag/documents").json()["documents"]}
        assert any(s["id"] == "mia" for s in c2.get("/api/skills").json()["skills"])
        assert "PERSIST_TEST" in c2.get("/api/mcp/keys").json()["configured"]
        assert os.environ.get("PERSIST_TEST") == "secreto"


# ── Entradas hostiles: nada puede devolver 500 ─────────────────────────────

def test_hostile_inputs_never_return_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        cases = [
            ("POST", "/api/rag/documents", {"id": "x" * 300, "text": "a"}),
            ("POST", "/api/rag/documents", {"id": "../../escape", "text": "a"}),
            ("GET", "/api/rag/query?q=&k=999", None),
            ("POST", "/api/skills/user", {"id": "../fuera", "name": "x",
                                          "description": "descripción de prueba"}),
            ("PUT", "/api/mcp/keys/K", {"value": "x" * 50000}),
            ("POST", "/api/feedback", {"request_id": None, "positive": "sí"}),
            ("PUT", "/api/memory/profile", {"text": "x" * 100000}),
            ("POST", "/api/documents/generate", {"content": "x", "format": "exe"}),
        ]
        for method, path, body in cases:
            r = c.request(method, path, json=body) if body is not None else c.request(method, path)
            assert r.status_code < 500, f"{method} {path} -> {r.status_code}"
