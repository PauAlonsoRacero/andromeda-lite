"""Quinto registro real (Audi TT, GTA 6) y memoria estilo Claude."""
import asyncio
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def _stream(texto):
    from app.core.output_filters import DateEchoFilter
    f = DateEchoFilter()
    return "".join(f.feed(ch) for ch in texto) + f.flush()


# ── "Hoy es viernes, 25 de septiembre de 2026, y son las 22:36." ───────────

def test_date_echo_is_removed_at_start():
    assert _stream("Hoy es viernes, 25 de septiembre de 2026, y son las 22:36.\n\n"
                   "GTA VI saldrá el 19 de noviembre.") == "GTA VI saldrá el 19 de noviembre."


def test_date_echo_is_removed_between_tool_rounds():
    t = "Uno.\n\nHoy es viernes, 25 de septiembre de 2026, y son las 22:48.\n\nDos."
    assert _stream(t) == "Uno.\n\nDos."


def test_date_filter_keeps_normal_text_and_paragraphs():
    t = "Hoy es un buen día para comprar.\n\n## Título\n\n- a\n- b"
    assert _stream(t) == t
    assert _stream("Today is Friday, September 25, 2026, and it is 22:36.\n\nOk.") == "Ok."


def test_date_prompt_asks_not_to_repeat_it():
    from app.specialists.identity import with_identity
    s = with_identity("x", "generalist", "gemma3:27b", user_prompt="hola")
    assert "NO lo menciones ni lo repitas" in s or "do NOT mention or repeat" in s


# ── JSON de herramientas en el texto visible ───────────────────────────────

def test_tool_call_json_never_leaks(monkeypatch):
    import app.mcp.executor as mx

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

    class _Cli:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, m, url, json=None, **k):
            if "Resultados de las herramientas" in json["messages"][-1]["content"]:
                return _Resp(["No he podido acceder."])
            return _Resp(["Entiendo tu frustración.\n\n", "<tool_call>", '{"tool": ',
                          '"fetch", "input": {"url": ', '"https://x.com"}}', "</tool_call>"])
    monkeypatch.setattr(mx.httpx, "AsyncClient", _Cli)

    class _Mgr:
        tools = [types.SimpleNamespace(name="fetch", description="f", input_schema={})]

        async def call_tool(self, n, a):
            return types.SimpleNamespace(text="404", is_error=True, error_msg="404")
    visto = []

    async def emit(t):
        visto.append(t)
    asyncio.run(mx.MCPExecutor(_Mgr()).stream_with_tools(
        prompt="p", model_name="m", system_prompt="s", ollama_url="http://x", on_token=emit))
    texto = "".join(visto)
    assert "fetch" not in texto and "input" not in texto and "</t" not in texto
    assert "Entiendo tu frustración." in texto


# ── Selector de herramientas ───────────────────────────────────────────────

def _T(n, d):
    return types.SimpleNamespace(name=n, description=d, server_id="x")


def test_web_tools_only_with_a_url_in_the_message():
    from app.mcp.executor import select_tools
    tools = [_T("fetch", "Fetches a URL from the internet"), _T("puppeteer_navigate", "Navigate to a URL")]
    for p in ("pues vaya mierda no?", "busca en internet cuando sale el gta 6"):
        assert select_tools(tools, p) == [], p
    assert select_tools(tools, "lee https://rockstargames.com/VI")


def test_selector_receives_only_the_user_message():
    import inspect
    from app.core import executor, streaming
    assert 'config.get("user_prompt") or prompt' in inspect.getsource(streaming)
    assert 'config.get("user_prompt") or prompt' in inspect.getsource(executor)


# ── Enlaces ───────────────────────────────────────────────────────────────

def test_web_results_ask_for_links():
    import inspect
    from app.core import prompt_builder
    src = inspect.getsource(prompt_builder)
    assert "[título](url)" in src and "Nunca digas que no puedes dar" in src


def test_error_messages_are_not_sent_as_history():
    assert "!m.error" in (SRC / "components/Chat.jsx").read_text(encoding="utf-8")


# ── "Sin especialistas activos" con 10 modelos instalados ─────────────────

def test_chat_falls_back_to_an_installed_model():
    from app.specialists.registry import SpecialistRegistry
    r = SpecialistRegistry("config/specialists.yaml")
    r.set_available_models(["gemma3:27b", "qwen3:8b"])
    for p in r.get_all():
        p.active = False
        if p.id == "generalist":
            p.model_name = "gemma3:27b"
    assert r.get_eligible_for_tier(3) == []
    respaldo = r.fallback_specialists(3)
    assert respaldo and respaldo[0].id == "generalist"


# ── Memoria estilo Claude ─────────────────────────────────────────────────

def _llenar(perfil):
    for k, v in [("nombre", "Me llamo Pau"), ("idioma", "Prefiero hablar en español"),
                 ("gustos:audi", "Me gusta el Audi TT"), ("objetivo:peso", "Quiero bajar de peso"),
                 ("proyecto:andromeda", "Trabajo en Andromeda"), ("persona:marc", "mi hermano se llama Marc"),
                 ("nota:x", "Tengo una reunión el lunes")]:
        perfil.upsert_fact(k, v)


def test_memory_is_grouped_like_claude(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        _llenar(c.app.state.memory_profile)
        d = c.get("/api/memory/files").json()
        secs = {s["id"]: {f["id"] for f in s["files"]} for s in d["sections"]}
        assert secs["tu"] == {"perfil", "preferencias"}
        assert {"gustos", "objetivos"} <= secs["temas"]
        assert secs["areas"] == {"proyectos"} and secs["personas"] == {"persona:marc"}
        assert secs["notas"] == {"notas"}
        archivo = next(f for s in d["sections"] for f in s["files"] if f["id"] == "gustos")
        assert archivo["updated"] > 0 and "Audi" in archivo["summary"]


def test_edit_and_delete_facts_and_files(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        p = c.app.state.memory_profile
        _llenar(p)
        c.put("/api/memory/profile/fact", json={"key": "gustos:audi", "text": "Me gusta el Audi TT mk1"})
        assert "mk1" in p.render()
        c.delete("/api/memory/profile/fact", params={"key": "nombre"})
        assert "Pau" not in p.render()
        r = c.delete("/api/memory/profile/file", params={"section": "temas", "file": "gustos"}).json()
        assert r["deleted"] == 1 and "Audi" not in p.render()


def test_turning_off_sensitive_purges_them(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        p = c.app.state.memory_profile
        _llenar(p)
        r = c.post("/api/memory/purge-sensitive").json()
        assert r["deleted"] >= 1 and r["failed"] == 0
        assert "bajar de peso" not in p.render() and "Audi" in p.render()


def test_import_from_another_assistant(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert "«- »" in c.get("/api/memory/import-prompt").json()["prompt"] or \
               '"- "' in c.get("/api/memory/import-prompt").json()["prompt"]
        texto = "Esto es lo que sé:\n- Me llamo Pau\n- Me gusta el Audi TT\n- Estudia ASIR en Badalona"
        r = c.post("/api/memory/import", json={"text": texto}).json()
        assert r["imported"] == 3
        render = c.app.state.memory_profile.render()
        assert "Pau" in render and "Audi" in render and "ASIR" in render


def test_people_are_recognised():
    from app.memory.extractor import extract_memories, topic_key
    r = extract_memories("mi hermano se llama Marc")
    assert r and topic_key(r[0][2], r[0][0]) == "persona:marc"


def test_search_past_conversations(tmp_path):
    from app.memory.structure import remite_a_conversaciones, search_past_chats
    ruta = tmp_path / "ui_state.json"
    ruta.write_text(json.dumps({"andromeda_conversations": [
        {"title": "Coche", "messages": [
            {"role": "user", "content": "quiero comprarme un audi tt mk1 barato"},
            {"role": "assistant", "content": "Mira en Milanuncios: https://www.milanuncios.com/audi-tt-mk1"}]},
        {"title": "Otra", "messages": [{"role": "user", "content": "receta de pasta carbonara"},
                                        {"role": "assistant", "content": "Huevo y guanciale."}]}]}))
    assert remite_a_conversaciones("¿recuerdas el audi tt que te dije?")
    assert not remite_a_conversaciones("cuándo sale gta 6")
    r = search_past_chats(ruta, "¿recuerdas el audi tt mk1 que te dije?")
    assert len(r) == 1 and "milanuncios" in r[0]["assistant"]


def test_conversation_search_toggle_is_wired():
    """El interruptor existía en la interfaz pero no hacía nada."""
    import inspect
    from app.core import prompt_builder, router
    from app.routes import chat
    assert "andromeda_mem_conversation_search" in inspect.getsource(prompt_builder.add_past_chats)
    assert "add_past_chats" in inspect.getsource(chat) and "add_past_chats" in inspect.getsource(router)


def test_memory_settings_live_in_memory_section():
    mf = (SRC / "components/MemoryFiles.jsx").read_text(encoding="utf-8")
    for k in ("memConversationSearch", "memAutogenerate", "memSensitive", "/api/memory/import"):
        assert k in mf, k


# ── Apariencia macOS ──────────────────────────────────────────────────────

def test_design_11_replaces_the_macos_theme():
    css = (SRC / "styles/index.css").read_text(encoding="utf-8")
    assert "body.design-11 .sidebar-anim" in css and "theme-macos" not in css
    assert "S.setDesign('1.1')" in (SRC / "components/SettingsPanel.jsx").read_text(encoding="utf-8")
