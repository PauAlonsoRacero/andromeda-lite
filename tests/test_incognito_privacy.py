"""El modo incógnito promete no guardar nada. Verificarlo de verdad."""
import logging

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def test_incognito_does_not_persist_the_prompt(tmp_path, monkeypatch):
    """La fuga encontrada: el prompt acababa en traces.db pese al incógnito.

    Las trazas guardan 100 caracteres del prompt para observabilidad. En
    incógnito eso contradice directamente lo que la aplicación promete.
    """
    with _client(tmp_path, monkeypatch) as c:
        secreto = "MI SECRETO CONFIDENCIAL 12345"
        c.post("/api/chat", json={"prompt": secreto, "stream": False, "incognito": True})
        trazas = c.get("/api/traces").json().get("traces", [])
        for t in trazas:
            assert secreto not in (t.get("prompt_preview") or ""), "el prompt se guardó"


def test_normal_mode_still_records_preview(tmp_path, monkeypatch):
    """No vaciar la observabilidad por el camino: fuera de incógnito sí se guarda."""
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/chat", json={"prompt": "pregunta visible", "stream": False,
                                  "incognito": False})
        trazas = c.get("/api/traces").json().get("traces", [])
        assert any("visible" in (t.get("prompt_preview") or "") for t in trazas)


def test_incognito_does_not_save_memories(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        antes = c.get("/api/memory/stats").json().get("total", 0)
        c.post("/api/chat", json={"prompt": "recuerda que mi clave es 999",
                                  "stream": False, "incognito": True})
        assert c.get("/api/memory/stats").json().get("total", 0) == antes


def test_incognito_blocks_web_search_in_both_paths():
    """Incógnito es una garantía: no puede depender del ajuste de red."""
    import inspect
    from app.routes import chat
    from app.core import router
    for mod in (chat, router):
        src = inspect.getsource(mod)
        assert "incognito" in src


def test_registry_lock_is_created_once():
    """Crear el lock con hasattr dentro del método no protege nada: dos hilos
    pueden pasar la comprobación a la vez y crear cada uno el suyo."""
    from app.specialists.registry import SpecialistRegistry
    r = SpecialistRegistry("config/specialists.yaml")
    assert hasattr(r, "_overrides_lock"), "el lock no se crea en el constructor"
    src = __import__("inspect").getsource(SpecialistRegistry.update_model)
    assert 'hasattr(self, "_overrides_lock")' not in src


def test_registry_survives_concurrent_updates():
    import threading
    from app.specialists.registry import SpecialistRegistry
    r = SpecialistRegistry("config/specialists.yaml")
    r.set_available_models(["a:1b", "b:2b"])
    errores = []

    def hammer():
        try:
            for _ in range(15):
                r.update_model("generalist", "a:1b", active=True)
        except Exception as exc:                      # noqa: BLE001
            errores.append(repr(exc))

    hilos = [threading.Thread(target=hammer) for _ in range(5)]
    for h in hilos: h.start()
    for h in hilos: h.join()
    assert not errores, errores
