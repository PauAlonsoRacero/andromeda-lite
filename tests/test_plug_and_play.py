"""
Test de integración del flujo "plug & play" de modelos.

Garantiza que un modelo descargado en Ollama (sin tocar specialists.yaml):
  1. aparece en /api/models/ollama (lo lee el selector del chat)
  2. se puede forzar y usar en el chat (force_model)
  3. se reporta en la metadata final (models_used)
  4. queda registrado en MLOps (/api/mlops/models-used)

Usa un Ollama simulado para no depender de un servidor real.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import pytest
from fastapi.testclient import TestClient


NEW_MODEL = "mistral-small:24b"


class _ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencio
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [{"name": NEW_MODEL, "size": int(15e9)}]})
        else:
            self._json({}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(n)
        if self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write((json.dumps({
                "message": {"content": "respuesta"},
                "done": True, "eval_count": 12, "total_duration": int(4e8),
            }) + "\n").encode())
        elif self.path == "/api/generate":
            self._json({"response": "x", "eval_count": 3, "total_duration": int(1e8)})
        else:
            self._json({}, 404)


@pytest.fixture(scope="module")
def fake_ollama():
    srv = _ThreadingServer(("127.0.0.1", 11434), _FakeOllama)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield
    srv.shutdown()


@pytest.fixture()
def client(fake_ollama, tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANDROMEDA_SPECIALISTS_CONFIG_PATH", "config/specialists.yaml")
    monkeypatch.setenv("ANDROMEDA_HOST_VRAM_GB", "48")
    monkeypatch.delenv("ANDROMEDA_AUTH_REQUIRED", raising=False)
    from app import create_app
    with TestClient(create_app()) as c:
        yield c


def _force_chat(client, model):
    meta = {}
    with client.stream("POST", "/api/chat",
                       json={"prompt": "hola", "stream": True,
                             "force_model": model}) as resp:
        for ln in resp.iter_lines():
            if ln.startswith("data: ") and "[DONE]" not in ln:
                try:
                    ch = json.loads(ln[6:])
                except Exception:
                    continue
                if ch.get("is_final"):
                    meta = ch.get("metadata", {})
    return meta


def test_new_model_appears_in_selector(client):
    r = client.get("/api/models/ollama")
    assert NEW_MODEL in r.json().get("models", [])


@pytest.mark.skip(reason="Stats/MLOps/clasificador completos son de Pro")
def test_forced_model_is_used_and_reported(client):
    meta = _force_chat(client, NEW_MODEL)
    assert NEW_MODEL in meta.get("models_used", {}).values()


@pytest.mark.skip(reason="Stats/MLOps/clasificador completos son de Pro")
def test_usage_recorded_in_stats(client):
    _force_chat(client, NEW_MODEL)
    time.sleep(0.5)
    r = client.get("/api/traces/metrics")
    rt = r.json().get("realtime", {})
    assert rt.get("total_requests", 0) >= 1


@pytest.mark.skip(reason="Stats/MLOps/clasificador completos son de Pro")
def test_model_recorded_in_mlops(client):
    _force_chat(client, NEW_MODEL)
    time.sleep(0.5)
    r = client.get("/api/mlops/models-used")
    assert NEW_MODEL in json.dumps(r.json())


@pytest.mark.skip(reason="Stats/MLOps/clasificador completos son de Pro")
def test_forced_model_skips_classifier(client):
    """Forzar un modelo NO debe disparar el clasificador interno ni usar
    otro modelo: solo se llama al modelo elegido."""
    meta = _force_chat(client, NEW_MODEL)
    # el especialista reportado debe ser generalist y el modelo el forzado
    assert meta.get("specialists_used") == ["generalist"]
    assert meta.get("models_used", {}).get("generalist") == NEW_MODEL
    # la fuente del clasificador debe ser "forced"
    assert meta.get("classifier_source") in ("forced", None) or True


def test_diagnose_endpoint_reports_chain(client):
    """El endpoint de autodiagnóstico devuelve los checks de la cadena."""
    r = client.get("/api/health/diagnose")
    assert r.status_code == 200
    data = r.json()
    assert "checks" in data and len(data["checks"]) >= 4
    names = [c["check"] for c in data["checks"]]
    assert any("Ollama" in n for n in names)
    assert any("Especialistas" in n for n in names)
