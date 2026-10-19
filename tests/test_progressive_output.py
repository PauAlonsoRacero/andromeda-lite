"""Respuesta progresiva en escritorio, fases visibles y frases multilingües."""
import asyncio
import json
import logging
import time
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Trabajos de chat consultables ─────────────────────────────────────────

def _job():
    return {"text": "", "phase": "thinking", "phrase": None, "specialist": None,
            "meta": None, "error": None, "done": False, "ts": time.time()}


class _FakeStream:
    """Imita la respuesta SSE de /api/chat."""
    def __init__(self, chunks):
        self.status_code = 200
        self._lines = [f"data: {json.dumps(c)}" for c in chunks] + ["data: [DONE]"]

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def aread(self): return b""

    async def aiter_lines(self):
        for linea in self._lines:
            yield linea


def _patch_client(monkeypatch, chunks):
    import httpx

    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def stream(self, *a, **k): return _FakeStream(chunks)

    monkeypatch.setattr(httpx, "AsyncClient", _C)


class _Req:
    class url:
        hostname = "127.0.0.1"
    base_url = "http://127.0.0.1:1/"
    app = None


def test_job_accumulates_text_and_phases(monkeypatch):
    from app.routes import chat_jobs as cj
    _patch_client(monkeypatch, [
        {"content": "", "is_final": False, "metadata": {"phase": "searching"}},
        {"content": "", "is_final": False, "metadata": {"placeholder": "Pensando…"}},
        {"content": "Hola ", "is_final": False, "metadata": {}, "specialist_id": "g"},
        {"content": "Pau", "is_final": False, "metadata": {}, "specialist_id": "g"},
        {"content": "", "is_final": True, "metadata": {"request_id": "r1", "web_used": True}},
    ])
    job = _job()
    asyncio.run(cj._run(job, _Req(), {"prompt": "x"}, {}))
    assert job["done"] and job["text"] == "Hola Pau"
    assert job["phase"] == "writing" and job["phrase"] == "Pensando…"
    assert job["meta"]["request_id"] == "r1"


def test_job_reports_backend_errors(monkeypatch):
    """Un Ollama caído debe llegar a la interfaz como error legible."""
    from app.routes import chat_jobs as cj
    _patch_client(monkeypatch, [
        {"content": "No se detecta Ollama", "is_final": True, "metadata": {"error": True}},
    ])
    job = _job()
    asyncio.run(cj._run(job, _Req(), {"prompt": "x"}, {}))
    assert job["done"] and "Ollama" in job["error"]["message"]


def test_poll_returns_only_new_text(tmp_path, monkeypatch):
    """La interfaz pide solo lo nuevo: si recibiera todo cada vez, duplicaría."""
    from app.routes import chat_jobs as cj
    with _client(tmp_path, monkeypatch) as c:
        cj._jobs["j1"] = {**_job(), "text": "Hola Pau", "phase": "writing"}
        d = c.get("/api/chat/jobs/j1", params={"since": 5}).json()
        assert d["delta"] == "Pau" and d["offset"] == 8 and d["done"] is False


def test_finished_job_is_released_after_delivery(tmp_path, monkeypatch):
    from app.routes import chat_jobs as cj
    with _client(tmp_path, monkeypatch) as c:
        cj._jobs["j2"] = {**_job(), "text": "fin", "done": True, "meta": {"a": 1}}
        d = c.get("/api/chat/jobs/j2", params={"since": 3}).json()
        assert d["done"] and d["meta"] == {"a": 1}
        assert "j2" not in cj._jobs, "el trabajo terminado no se libera"


def test_unknown_job_is_404(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/chat/jobs/no-existe").status_code == 404


def test_cancel_stops_the_job(tmp_path, monkeypatch):
    from app.routes import chat_jobs as cj
    with _client(tmp_path, monkeypatch) as c:
        cj._jobs["j3"] = _job()
        assert c.delete("/api/chat/jobs/j3").json()["cancelled"] is True
        assert "j3" not in cj._jobs


def test_old_jobs_are_purged():
    """Un trabajo abandonado (ventana cerrada) no puede quedarse para siempre."""
    from app.routes import chat_jobs as cj
    cj._jobs["viejo"] = {**_job(), "ts": time.time() - 10_000}
    cj._purge()
    assert "viejo" not in cj._jobs


# ── Interfaz de escritorio ────────────────────────────────────────────────

def test_desktop_uses_progressive_jobs():
    """Antes pedía la respuesta entera y la pintaba de golpe tras 15-30 s."""
    src = (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")
    assert "/api/chat/jobs" in src
    assert "createSmoother" in src, "el texto aparecería a saltos"


def test_phases_are_shown_and_translated():
    sse = (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")
    assert "chunk.metadata?.phase" in sse
    i18n = (ROOT / "frontend/src/stores/i18n.js").read_text(encoding="utf-8")
    for k in ("phase.thinking", "phase.searching", "phase.writing"):
        assert f"'{k}'" in i18n


def test_search_phase_is_emitted_before_searching():
    """La búsqueda puede tardar varios segundos: hay que decirlo ANTES."""
    import inspect
    from app.routes import chat
    src = inspect.getsource(chat)
    assert src.index('"phase": "searching"') < src.index("await pb.add_web_context(")


# ── Frases de espera en el idioma de la interfaz ──────────────────────────

def test_loading_phrases_follow_the_language(monkeypatch):
    from app.core.linear_orchestrator import loading_phrase
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "en")
    assert loading_phrase("mid", prompt="create a file") in (
        "Creating the file…", "Preparing the file…")
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "fr")
    assert loading_phrase("mid", prompt="crée un fichier") == "Création du fichier…"


def test_every_language_has_every_phrase_category():
    from app.core.linear_orchestrator import _FRASES
    claves = set(_FRASES["es"])
    for lang, frases in _FRASES.items():
        assert set(frases) == claves, f"a {lang} le faltan: {claves - set(frases)}"
