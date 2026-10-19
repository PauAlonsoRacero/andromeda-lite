"""Fallos encontrados en el primer registro de diagnóstico real (M4 Max).

Cada test corresponde a una línea concreta de aquel registro.
"""
import asyncio
import json
import logging
import time
import types

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# "⚠️ Demasiadas peticiones. Espera 26s." ────────────────────────────────────

def _app_limitada():
    """App mínima con el limitador real: sin arrancar Andromeda entera."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.middleware import RateLimitMiddleware
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.state.internal_token = "secreto-del-proceso"

    @app.post("/api/chat")
    async def chat():
        return {"ok": True}

    @app.get("/api/chat/jobs/{jid}")
    async def poll(jid: str):
        return {"ok": True}
    return TestClient(app)


def test_progress_polling_is_not_rate_limited():
    """El sondeo cada ~100 ms contaba contra el límite del chat (20/min)."""
    c = _app_limitada()
    codigos = [c.get("/api/chat/jobs/x").status_code for _ in range(60)]
    assert 429 not in codigos


def test_internal_call_is_exempt_only_with_the_real_token():
    """La exención interna no puede ser una puerta trasera al limitador."""
    c = _app_limitada()
    reales = [c.post("/api/chat", headers={"X-Andromeda-Internal": "secreto-del-proceso"}
                     ).status_code for _ in range(25)]
    assert 429 not in reales
    falsos = [c.post("/api/chat", headers={"X-Andromeda-Internal": "falso"}).status_code
              for _ in range(25)]
    assert 429 in falsos


# "mcp: respuesta con herramientas: 0 llamadas" tras 14,6 s ──────────────────

def test_tool_loop_only_with_real_connectors():
    """Las 7 herramientas eran las integradas de archivos, presentes siempre."""
    from app.mcp.manager import MCPManager
    m = MCPManager(config_path="config/mcp_servers.yaml")
    m._rebuild_tools()
    assert m.tools, "deberían existir las integradas"
    assert m.has_external_tools is False, "sin conectores no debe activarse el bucle"


class _Ollama:
    """Ollama falso en streaming (NDJSON) para el bucle de herramientas."""
    def __init__(self, respuestas):
        self.respuestas = respuestas

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, json=None, **k):
        ultimo = json["messages"][-1]["content"]
        partes = next(v for clave, v in self.respuestas if clave in ultimo)
        return _Resp(partes)


class _Resp:
    def __init__(self, partes):
        self.partes = partes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for p in self.partes:
            yield json.dumps({"message": {"content": p}})


def _run_tools(monkeypatch, prompt, respuestas):
    import app.mcp.executor as mx
    monkeypatch.setattr(mx.httpx, "AsyncClient", _Ollama(respuestas))

    class _Res:
        text, is_error, error_msg = "14:05", False, None

    class _Mgr:
        tools = [types.SimpleNamespace(name="get_time", description="hora", input_schema={})]

        async def call_tool(self, n, a):
            return _Res()

    emitidos = []

    async def emit(t):
        emitidos.append(t)

    texto, log = asyncio.run(mx.MCPExecutor(_Mgr()).stream_with_tools(
        prompt=prompt, model_name="m", system_prompt="s",
        ollama_url="http://x", on_token=emit))
    return emitidos, log


def test_tool_loop_streams_normal_answers(monkeypatch):
    """Antes: silencio hasta el final. Ahora: varios trozos, en directo."""
    emitidos, log = _run_tools(monkeypatch, "tcp vs udp", [
        ("tcp", ["<think>", "razono", "</think>", "TCP ", "fiable, ", "UDP ", "no."])])
    assert len(emitidos) > 1
    assert "".join(emitidos) == "TCP fiable, UDP no."
    assert "razono" not in "".join(emitidos), "se mostró el razonamiento interno"
    assert log == []


def test_tool_call_is_hidden_and_executed(monkeypatch):
    emitidos, log = _run_tools(monkeypatch, "qué hora es", [
        ("Resultados de las herramientas", ["Son ", "las ", "14:05."]),
        ("hora", ['<tool_call>{"tool": "get_time", "input": {}}</tool_call>'])])
    visible = "".join(emitidos)
    assert "tool_call" not in visible and visible == "Son las 14:05."
    assert [x["tool"] for x in log] == ["get_time"]


# "memory  perfil incluido  | It please." ────────────────────────────────────

def test_stored_junk_is_cleaned_on_load(tmp_path):
    """El extractor ya no genera basura, pero la antigua seguía guardada."""
    from app.memory.profile import MemoryProfile
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"facts": {"idioma": "I prefer to talk in English",
                                       "nota:it please": "It please."}, "manual": ""}))
    mp = MemoryProfile(p)
    assert "It please" not in mp.render()
    assert "English" in mp.render()
    assert "nota:it please" not in json.loads(p.read_text())["facts"]


def test_junk_is_never_stored(tmp_path):
    from app.memory.profile import MemoryProfile
    mp = MemoryProfile(tmp_path / "p.json")
    mp.upsert_fact("nota:x", "It please.")
    assert mp.render().strip() == ""


# "¿buscar en internet? SÍ" para TCP vs UDP ─────────────────────────────────

def test_opening_question_mark_is_not_a_proper_noun():
    """Con "¿" delante, "Cuál" se tomaba por nombre propio: CUALQUIER pregunta
    en español que empezara por ¿ buscaba en internet."""
    from app.core.web_search import needs_web_search
    for p in ("¿Cuál es la diferencia entre TCP y UDP?", "¿Qué es un puntero?",
              "¿Cómo funciona DNS?"):
        assert not needs_web_search(p), p
    assert needs_web_search("¿Quién es Pedro Sánchez?")


# Resultados web solo con títulos ───────────────────────────────────────────

def test_ddg_html_parser_extracts_snippets():
    """`título.*?(snippet)?` se saltaba el texto siempre (.*? perezoso)."""
    from app.core.web_search import _parse_ddg_html
    html = ('<a class="result__a" href="https://a.com">TCP vs UDP</a>'
            '<a class="result__snippet" href="x">TCP garantiza la entrega.</a>'
            '<a class="result__a" href="https://b.com">UDP</a>'
            '<div class="result__snippet">UDP no garantiza el orden.</div>')
    r = _parse_ddg_html(html, 5)
    assert [x["snippet"] for x in r] == ["TCP garantiza la entrega.", "UDP no garantiza el orden."]


def test_no_fake_duplicate_engine():
    """"startpage" era DuckDuckGo Lite con otro nombre: petición duplicada."""
    import inspect
    from app.core import web_search
    assert "_search_startpage" not in inspect.getsource(web_search)


# "HISTORIAL: Usuario: ¿Cuál es…" + la misma pregunta ───────────────────────

def test_current_message_is_not_repeated_in_history():
    from app.core import prompt_builder as pb
    p = pb.PromptParts(message="¿Cuál es la diferencia entre TCP y UDP?")
    asyncio.run(pb.add_history(p, [{"role": "user",
                                    "content": "¿Cuál es la diferencia entre TCP y UDP?"}], 8))
    assert p.render().count("TCP y UDP") == 1


# "ram_gb: 0" en un M4 Max ───────────────────────────────────────────────────

def test_ram_is_read_from_the_right_field():
    """Se leía `total_ram_gb`, pero el campo es `ram_total_gb`: la RAM era
    siempre 0 y, sin GPU, el contexto se quedaba en el mínimo."""
    from app.core.inference_tuning import options_from_hardware
    hw = types.SimpleNamespace(ram_total_gb=32, total_vram_gb=0, cpu_cores=8,
                               acceleration="cpu")
    assert options_from_hardware({}, hw)["num_ctx"] > 4096
