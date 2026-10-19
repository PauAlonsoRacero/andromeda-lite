"""El camino de la app de ESCRITORIO (sin streaming) debe tener todo.

La app de escritorio no puede usar streaming (WKWebView en macOS no entrega el
cuerpo de forma incremental), así que va siempre por el camino sin streaming.
Durante semanas la búsqueda web, la lectura de URLs y SearXNG vivieron solo en
el camino streaming: en la aplicación principal no se ejecutaban nunca, por
muchas mejoras que se hicieran. Estos tests prueban ese camino directamente.
"""
import logging
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def _fake_model(monkeypatch, texto="Respuesta simulada del modelo."):
    """Sin Ollama la respuesta sale por el camino de error, que no lleva los
    metadatos de uso. Estos tests pasaban antes por casualidad: el bucle de
    herramientas integradas devolvía algo aunque fallara."""
    import app.core.executor as ex

    async def modelo(specialist, prompt, config, **kw):
        return {"specialist_id": specialist.id, "model_name": "qwen3:14b",
                "content": texto, "latency_ms": 50.0, "success": True, "ttft_ms": 20.0}
    monkeypatch.setattr(ex, "call_with_fallback", modelo)


def _fake_search(monkeypatch, llamadas):
    import app.core.web_search as ws

    async def falso(q, max_results=4, timeout=8.0):
        llamadas.append(q)
        return [{"title": "GTA VI", "snippet": "Sale el 19 de noviembre de 2026",
                 "url": "https://ejemplo.com"}]
    monkeypatch.setattr(ws, "search_web", falso)


def test_desktop_uses_the_non_streaming_path():
    """Deja constancia de POR QUÉ importa este camino."""
    src = (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")
    assert "pywebview" in src and "stream: false" in src


def test_desktop_path_searches_the_web(tmp_path, monkeypatch):
    _fake_model(monkeypatch)
    llamadas = []
    _fake_search(monkeypatch, llamadas)
    with _client(tmp_path, monkeypatch) as c:
        c.app.state.registry.set_available_models(["qwen3:14b"])
        r = c.post("/api/chat", json={"prompt": "when is gta 6 launching on ps5?",
                                      "stream": False}).json()
        assert llamadas, "el camino de escritorio no buscó en internet"
        assert r["web_used"] is True


def test_desktop_path_injects_results_into_the_prompt(tmp_path, monkeypatch):
    from app.observability import diagnostics as diag
    _fake_search(monkeypatch, [])
    with _client(tmp_path, monkeypatch) as c:
        diag.set_enabled(True)
        diag.clear()
        c.post("/api/chat", json={"prompt": "when is gta 6 launching?", "stream": False})
        prompts = [e for e in diag.get_events() if e["category"] == "prompt"]
        diag.set_enabled(False)
        assert prompts and "19 de noviembre" in prompts[-1]["detail"]


def test_desktop_path_respects_incognito(tmp_path, monkeypatch):
    llamadas = []
    _fake_search(monkeypatch, llamadas)
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/chat", json={"prompt": "when is gta 6 launching?",
                                  "stream": False, "incognito": True})
        assert llamadas == [], "buscó en internet en modo incógnito"


def test_desktop_response_reports_what_was_used(tmp_path, monkeypatch):
    _fake_model(monkeypatch)
    """Sin esto, los indicadores de skill, fuentes y web no salían en escritorio."""
    _fake_search(monkeypatch, [])
    with _client(tmp_path, monkeypatch) as c:
        c.app.state.registry.set_available_models(["qwen3:14b"])
        c.post("/api/rag/documents", json={"id": "manual.md",
                                           "text": "El puerto de Andromeda es el 8765"})
        r = c.post("/api/chat", json={
            "prompt": "revisa este código y dime qué puerto usa andromeda",
            "stream": False}).json()
        assert r["skill_used"] == "Code Review"
        assert r["rag_sources"] == ["manual.md"]


def test_web_logic_lives_in_one_place():
    """Una sola implementación compartida: no puede volver a desincronizarse."""
    import inspect
    from app.core import router
    from app.routes import chat
    assert "add_web_context" in inspect.getsource(router)
    assert "add_web_context" in inspect.getsource(chat)
    assert "search_web(" not in inspect.getsource(chat), \
        "la búsqueda sigue implementada dentro de chat.py"


def test_post_response_work_does_not_block(tmp_path, monkeypatch):
    """Guardar memoria puede tardar hasta 10 s (embeddings): no debe retrasar
    la respuesta en ninguno de los dos caminos."""
    import inspect
    from app.routes import chat
    src = inspect.getsource(chat)
    assert src.count("_spawn_background(_after_response(") == 2
    assert "await _after_response(" not in src


def test_no_hardcoded_spanish_in_chat_services():
    for f in ("frontend/src/services/sse.js", "frontend/src/stores/chat.js"):
        src = (ROOT / f).read_text(encoding="utf-8")
        for texto in ("'Pensando…'", "'Error de red'", "'Nueva conversación'",
                      "'Error desconocido'"):
            assert texto not in src, f"{f} tiene {texto} sin traducir"


def test_desktop_path_creates_files_end_to_end(tmp_path, monkeypatch):
    """El fallo: los bloques ```andromeda:write``` solo se ejecutaban en el
    camino streaming. En escritorio el modelo los emitía y nadie los ejecutaba.

    Esta prueba recorre el camino COMPLETO de escritorio con un modelo simulado,
    no la función suelta: probar la pieza aislada es justo lo que ocultó el fallo.
    """
    import os
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(ws))
    import app.core.executor as ex

    bloque = 'Aquí tienes:\n\n```andromeda:write path="hola.html"\n<h1>Hola</h1>\n```\n'

    async def modelo_falso(specialist, prompt, config, **kw):
        return {"specialist_id": specialist.id, "model_name": "qwen3:14b",
                "content": bloque, "latency_ms": 100.0, "success": True, "ttft_ms": 30.0}
    monkeypatch.setattr(ex, "call_with_fallback", modelo_falso)

    with _client(tmp_path, monkeypatch) as c:
        c.app.state.registry.set_available_models(["qwen3:14b"])
        r = c.post("/api/chat", json={"prompt": "crea un archivo hola.html",
                                      "stream": False}).json()
        assert r.get("file_actions"), "no se ejecutó ninguna acción de archivo"
        assert r["file_actions"][0]["ok"] is True
        assert os.path.exists(ws / "hola.html"), "el archivo no llegó a disco"


def test_file_actions_live_in_one_place():
    import inspect
    from app.core import router
    from app.routes import chat
    assert "run_for_response" in inspect.getsource(router)
    assert "run_for_response" in inspect.getsource(chat)
    assert "execute_actions(" not in inspect.getsource(chat)
