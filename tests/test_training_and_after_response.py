"""Corpus de entrenamiento para Apolo, y efectos posteriores a la respuesta."""
import asyncio
import json
import logging
import types

logging.disable(logging.CRITICAL)


def _corpus(tmp_path, enabled=True):
    from app.mlops.training_corpus import TrainingCorpus
    c = TrainingCorpus(tmp_path)
    c.set_enabled(enabled)
    return c


_RESP = "Una respuesta suficientemente larga y útil para servir de ejemplo de entrenamiento."


# ── Corpus ─────────────────────────────────────────────────────────────────

def test_disabled_by_default(tmp_path):
    """Guarda conversaciones completas en disco: solo si el usuario lo pide."""
    from app.mlops.training_corpus import TrainingCorpus
    c = TrainingCorpus(tmp_path)
    assert c.is_enabled() is False
    assert c.record("r1", "hola", _RESP) is False


def test_never_records_incognito(tmp_path):
    c = _corpus(tmp_path)
    assert c.record("r1", "secreto", _RESP, incognito=True) is False
    assert c.stats()["total"] == 0


def test_trivial_answers_are_skipped(tmp_path):
    """Un 'ok' no enseña nada al modelo."""
    c = _corpus(tmp_path)
    assert c.record("r1", "hola", "ok") is False


def test_votes_attach_to_samples(tmp_path):
    c = _corpus(tmp_path)
    c.record("r1", "pregunta", _RESP)
    c.rate("r1", True)
    assert c.stats()["positive"] == 1


def test_vote_before_record_is_not_lost(tmp_path):
    """Si el voto llega antes de guardar, al guardar se conserva."""
    c = _corpus(tmp_path)
    c.record("r1", "pregunta", _RESP)
    c.rate("r1", False)
    c.record("r1", "pregunta", _RESP)          # re-guardado (INSERT OR REPLACE)
    assert c.stats()["negative"] == 1


def test_export_excludes_bad_and_unrated(tmp_path):
    """Entrenar con respuestas marcadas como malas enseña justo lo contrario."""
    c = _corpus(tmp_path)
    for i in range(15):
        c.record(f"r{i}", f"pregunta {i}", _RESP)
        if i < 10:
            c.rate(f"r{i}", True)
        elif i < 13:
            c.rate(f"r{i}", False)
    r = c.export_mlx(tmp_path / "out")
    assert r["train"] + r["valid"] == 10


def test_export_format_matches_mlx(tmp_path):
    """Formato chat de mlx_lm: {"messages": [{role, content}, ...]}."""
    c = _corpus(tmp_path)
    for i in range(12):
        c.record(f"r{i}", f"pregunta {i}", _RESP,
                 history=[{"role": "user", "content": "antes"},
                          {"role": "assistant", "content": "respuesta previa"}])
        c.rate(f"r{i}", True)
    r = c.export_mlx(tmp_path / "out")
    assert r["valid"] >= 1, "sin conjunto de validación no se detecta el sobreajuste"
    ej = json.loads((tmp_path / "out" / "train.jsonl").read_text().splitlines()[0])
    roles = [m["role"] for m in ej["messages"]]
    assert roles[-2:] == ["user", "assistant"] and roles[0] == "user"


# ── Efectos posteriores a la respuesta: el bug de la memoria ───────────────

def test_streaming_path_runs_after_response():
    """El bug: la extracción de memoria solo existía en el camino no-streaming,
    y el streaming (el modo normal) retorna antes. "Recuerda que me llamo Pau"
    no se guardaba nunca en uso real."""
    import inspect
    from app.routes import chat
    src = inspect.getsource(chat)
    pos_after = src.index("_spawn_background(_after_response(")
    pos_stream_return = src.index("return StreamingResponse(")
    assert pos_after < pos_stream_return, \
        "el camino streaming no ejecuta la memoria antes de devolver la respuesta"
    assert src.count("_spawn_background(_after_response(") >= 2, "no se usa en los dos caminos"


def test_after_response_saves_memory_and_sample(tmp_path, monkeypatch):
    """Funcional: memoria y corpus desde la misma función común."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    from app.routes.chat import _after_response
    with TestClient(create_app()) as c:
        st = c.app.state
        st.training_corpus.set_enabled(True)
        req = types.SimpleNamespace(app=c.app)
        chat_req = types.SimpleNamespace(
            prompt="me llamo Pau", incognito=False, conversation_history=[])
        asyncio.run(_after_response(req, chat_req, response_text=_RESP,
                                    request_id="x1", model="qwen3:14b"))
        assert "Pau" in st.memory_profile.render(), "la memoria no se guardó"
        assert st.training_corpus.stats()["total"] == 1


def test_after_response_respects_incognito(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    from app.routes.chat import _after_response
    with TestClient(create_app()) as c:
        st = c.app.state
        st.training_corpus.set_enabled(True)
        req = types.SimpleNamespace(app=c.app)
        chat_req = types.SimpleNamespace(
            prompt="me llamo Pau", incognito=True, conversation_history=[])
        asyncio.run(_after_response(req, chat_req, response_text=_RESP,
                                    request_id="x2", model="m"))
        assert "Pau" not in (st.memory_profile.render() or "")
        assert st.training_corpus.stats()["total"] == 0


def test_training_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.get("/api/training").json()["enabled"] is False
        assert c.put("/api/training", json={"enabled": True}).json()["enabled"] is True
        r = c.post("/api/training/export", json={}).json()
        assert "command" in r and "mlx_lm.lora" in r["command"]
