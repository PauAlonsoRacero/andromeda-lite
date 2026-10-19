"""Fallos del segundo registro de diagnóstico real (M4 Max, 6 conectores MCP).

Cada bloque corresponde a algo que se vio en aquel registro o que Pau reportó.
"""
import asyncio
import base64
import json
import logging
import types
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Memoria: "le digo que me gusta el azul y no lo guarda" ─────────────────

def test_new_patterns_capture_goals_and_favourites():
    from app.memory.extractor import extract_memories
    casos = {
        "me gustaría bajar de peso": "objetivo",
        "quiero bajar de peso": "objetivo",
        "I want to lose weight": "objetivo",
        "mi color favorito es el azul": "favoritos",
        "my favourite colour is blue": "favoritos",
        "j'aime le football": "gustos",
        "我喜欢蓝色": "gustos",
    }
    for frase, tema in casos.items():
        temas = [t for _, _, t in extract_memories(frase)]
        assert tema in temas, f"{frase!r} → {temas}"


def test_likes_accumulate_instead_of_replacing(tmp_path):
    """El fallo real: cada gusto nuevo sobrescribía el anterior (un tema = un dato)."""
    from app.memory.extractor import extract_memories, topic_key
    from app.memory.profile import MemoryProfile
    perfil = MemoryProfile(tmp_path / "p.json")
    for frase in ("me gusta el color azul", "me gusta el fútbol"):
        for contenido, _, tema in extract_memories(frase):
            perfil.upsert_fact(topic_key(tema, contenido), contenido)
    texto = perfil.render().lower()
    assert "azul" in texto and "fútbol" in texto


def test_single_value_topics_still_replace():
    from app.memory.extractor import topic_key
    assert topic_key("nombre", "me llamo Pau") == "nombre"
    assert topic_key("gustos", "me gusta el azul") != topic_key("gustos", "me gusta el fútbol")


def test_junk_explicit_captures_are_rejected():
    from app.memory.extractor import extract_memories
    assert extract_memories("remember this. 42") == []


def test_memory_prefix_is_stripped():
    """Se guardaba literalmente "In andromeda's memory the iphone duo…"."""
    from app.memory.extractor import extract_memories
    r = extract_memories("save in andromeda memory the iphone duo capabilities")
    assert r and not r[0][0].lower().startswith("in ")


# ── Memoria: "cuando intento borrarla no funciona" ─────────────────────────

def _perfil_con_datos(tmp_path):
    from app.memory.profile import MemoryProfile
    p = MemoryProfile(tmp_path / "p.json")
    p.upsert_fact("gustos:azul", "Me gusta el color azul")
    p.upsert_fact("gustos:futbol", "Me gusta el fútbol")
    p.set_manual("Notas escritas a mano")
    return p


def test_clear_memory_command_in_several_languages(tmp_path):
    """El modelo usaba el conector MCP "memory" (otro sistema) y fallaba."""
    from app.core import prompt_builder as pb
    for orden in ("borra la memoria", "clear the info in andromedas memory please",
                  "vergiss alles in deinem Gedächtnis", "efface ta mémoire"):
        perfil = _perfil_con_datos(tmp_path)
        partes = pb.PromptParts(message=orden)
        r = asyncio.run(pb.handle_memory_commands(partes, orden, perfil, None, False))
        assert r == "cleared", orden
        assert "azul" not in perfil.render().lower()
        assert "Notas escritas a mano" in perfil.render(), "borró las notas del usuario"
        assert partes.meta.get("memory_command") == "cleared"


def test_forget_specific_fact(tmp_path):
    from app.core import prompt_builder as pb
    perfil = _perfil_con_datos(tmp_path)
    asyncio.run(pb.handle_memory_commands(pb.PromptParts(message="x"),
                                          "olvida que me gusta el azul", perfil, None, False))
    texto = perfil.render().lower()
    assert "azul" not in texto and "fútbol" in texto


def test_memory_commands_disable_mcp_tools():
    """Si no, el modelo volvía a tirar del conector MCP "memory"."""
    import inspect
    from app.core import router
    from app.routes import chat
    assert 'parts.meta.get("memory_command")' in inspect.getsource(router)
    assert '_parts.meta.get("memory_command")' in inspect.getsource(chat)


def test_memory_commands_ignored_in_incognito(tmp_path):
    from app.core import prompt_builder as pb
    perfil = _perfil_con_datos(tmp_path)
    r = asyncio.run(pb.handle_memory_commands(pb.PromptParts(message="x"),
                                              "borra la memoria", perfil, None, True))
    assert r is None and "azul" in perfil.render().lower()


# ── Búsqueda: busca en internet al pedirle crear una web ──────────────────

def test_creation_requests_do_not_search():
    from app.core.web_search import needs_web_search
    for p in ("quiero que me crees una página web en html",
              "mejora la página web porfavor",
              "create a web page with a nav bar",
              "tiene que ser con este diseño, cuando abro la pagina web se ve igual"):
        assert not needs_web_search(p), p


def test_explicit_search_still_works():
    from app.core.web_search import needs_web_search
    for p in ("search in the web the best phone out in the market right now",
              "busca en la web el mejor móvil", "cuándo sale gta 6"):
        assert needs_web_search(p), p


def test_ads_are_removed_and_redirects_unwrapped():
    from app.core.web_search import _limpiar_resultados
    r = _limpiar_resultados([
        {"title": "Anuncio", "snippet": "", "url": "https://duckduckgo.com/y.js?ad_domain=amazon.es"},
        {"title": "Real", "snippet": "", "url": "//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.com%2Fx&rut=1"},
    ])
    assert [x["url"] for x in r] == ["https://a.com/x"]


# ── Herramientas: 52 en cada mensaje ───────────────────────────────────────

def _T(nombre, desc, servidor="x"):
    return types.SimpleNamespace(name=nombre, description=desc, server_id=servidor)


_TOOLS = [_T("write_file", "Create or overwrite a file", "filesystem"),
          _T("edit_file", "Make line-based edits to a file", "filesystem"),
          _T("fetch", "Fetches a URL from the internet and extracts its contents", "fetch"),
          _T("get_current_time", "Get current time in a timezone", "time"),
          _T("delete_observations", "Delete observations from entities in the knowledge graph", "memory"),
          _T("write_file", "Crea un archivo", "builtin-fs")]


def test_no_tools_for_ordinary_requests():
    from app.mcp.executor import select_tools
    for p in ("quiero que me crees una página web en html", "explain pointers in C",
              "clear the info in andromedas memory please"):
        assert select_tools(_TOOLS, p) == [], p


def test_relevant_tools_are_selected():
    from app.mcp.executor import select_tools
    assert [t.name for t in select_tools(_TOOLS, "lee https://a.com/x")] == ["fetch"]
    assert [t.name for t in select_tools(_TOOLS, "what time is it in tokyo")] == ["get_current_time"]


def test_file_writing_tools_are_never_offered():
    """Chocaban con andromeda:write: edit_file falló y el modelo dijo que lo hizo."""
    from app.mcp.executor import select_tools
    elegidas = select_tools(_TOOLS, "write edit file create overwrite")
    assert not any(t.name in ("write_file", "edit_file") for t in elegidas)


def test_history_is_summarised_not_truncated():
    """El historial mostraba "0;\\n background: #f4f4f4;" (medio bloque de código)."""
    from app.core.prompt_builder import _resumir_turno
    t = _resumir_turno('Hecho:\n```andromeda:write path="web.html"\n<html>...</html>\n```')
    assert t == "Hecho:\n[guardó el archivo web.html]"
    assert "edit_file" not in _resumir_turno('Voy {"tool": "edit_file", "input": {}} ya')


# ── Longitud de respuesta: la página se guardaba truncada ─────────────────

def test_default_response_length_fits_a_web_page():
    from app.models.schemas import ChatRequest
    assert ChatRequest(prompt="x").max_tokens >= 8192
    assert "maxTokens = 8192" in (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")


def test_response_length_is_capped_by_context():
    from app.core.inference_tuning import options_from_hardware
    peq = types.SimpleNamespace(ram_total_gb=8, total_vram_gb=0, cpu_cores=4, acceleration="cpu")
    o = options_from_hardware({"num_predict": 8192}, peq)
    assert o["num_predict"] < o["num_ctx"], "la respuesta no deja sitio al prompt"


# ── Imágenes ──────────────────────────────────────────────────────────────

def test_vision_model_detection():
    from app.core.vision import is_vision_model, pick_vision_model
    assert is_vision_model("gemma3:27b") and not is_vision_model("gemma3:1b")
    assert not is_vision_model("qwen3:8b")
    assert pick_vision_model(["qwen3:8b", "llava:7b", "gemma3:27b"]) == "gemma3:27b"
    assert pick_vision_model(["qwen3:8b"]) is None


def test_registry_exposes_installed_models():
    """Se leía `available_models` sin existir: la lista era siempre [] y la visión
    habría dicho siempre que no había modelo instalado."""
    from app.specialists.registry import SpecialistRegistry
    r = SpecialistRegistry("config/specialists.yaml")
    r.set_available_models(["gemma3:27b"])
    assert r.available_models == ["gemma3:27b"]


def test_vision_instruction_uses_interface_language(monkeypatch):
    """llava recibía la pregunta del usuario y respondió en portugués."""
    from app.core import vision
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "es")
    assert "español" in vision._INSTRUCCION[vision._idioma()]


def test_images_reach_a_vision_chat_model():
    from app.core.streaming import _mensaje_usuario
    m = _mensaje_usuario("¿qué ves?", {"images": ["data:image/png;base64,AAAA"]})
    assert m["images"] == ["AAAA"]
    assert "images" not in _mensaje_usuario("hola", {})


def test_images_are_shown_in_the_chat():
    bubble = (ROOT / "frontend/src/components/MessageBubble.jsx").read_text(encoding="utf-8")
    chat = (ROOT / "frontend/src/components/Chat.jsx").read_text(encoding="utf-8")
    assert "message.attachments?.images" in bubble
    assert "miniatura(" in chat, "guardaría imágenes enteras en el almacenamiento local"


# ── Artefactos: "se ve igual que la primera versión" ──────────────────────

def test_preview_is_never_cached(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.html").write_text("<h1>v2</h1>")
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(ws))
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/api/files/raw", params={"path": "a.html"})
        assert "no-store" in r.headers.get("cache-control", "")


def test_preview_iframe_is_isolated():
    """allow-scripts + allow-same-origin deja que la página llame a la API."""
    src = (ROOT / "frontend/src/components/ArtifactsPanel.jsx").read_text(encoding="utf-8")
    assert "allow-same-origin" not in src


# ── Proyectos ─────────────────────────────────────────────────────────────

def _b64(t):
    return base64.b64encode(t.encode()).decode()


def test_project_files_keep_folder_structure(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/projects/proj-1234/files", json={"files": [
            {"path": "web/index.html", "content_b64": _b64("<h1>Tienda</h1>")},
            {"path": "web/css/estilo.css", "content_b64": _b64("body{}")},
        ]}).json()
        assert {f["path"] for f in r["files"]} == {"web/index.html", "web/css/estilo.css"}


def test_project_paths_cannot_escape(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/projects/proj-1234/files", json={"files": [
            {"path": "../fuera.txt", "content_b64": _b64("x")}]}).json()
        assert r["errors"] and not r["saved"]
        assert c.get("/api/projects/..%2Fx/files").status_code in (400, 404)


def test_project_context_reaches_the_model(tmp_path, monkeypatch):
    """Antes las instrucciones del proyecto nunca llegaban al modelo."""
    from app.core import prompt_builder as pb
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/projects/proj-1234/files", json={"files": [
            {"path": "notas.md", "content_b64": _b64("El cliente se llama Acme")}]})
        req = types.SimpleNamespace(project_id="proj-1234", project_name="Web",
                                    project_instructions="Responde en tono formal.",
                                    prompt="¿cómo se llama el cliente?", incognito=False)
        partes = pb.PromptParts(message=req.prompt)
        assert pb.add_project(partes, req)
        assert "tono formal" in partes.documents and "Acme" in partes.documents


def test_files_written_in_a_project_stay_in_it(tmp_path, monkeypatch):
    from app.core.file_actions import run_for_response
    with _client(tmp_path, monkeypatch) as c:
        run_for_response('```andromeda:write path="src/app.py"\nprint(1)\n```',
                         settings=c.app.state.settings, incognito=False,
                         project_id="proj-1234")
    assert (tmp_path / "projects/proj-1234/files/src/app.py").read_text().strip() == "print(1)"


def test_frontend_sends_the_project():
    sse = (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")
    assert sse.count("project_instructions") >= 3, "sse.js descarta los campos del proyecto"
    app = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    assert "newConversation(pid)" in app, "la conversación nueva no se vincula al proyecto"


# ── Potencia ──────────────────────────────────────────────────────────────

def test_power_selector_explains_itself():
    src = (ROOT / "frontend/src/components/ChatSettings.jsx").read_text(encoding="utf-8")
    assert "cs.power_explain" in src and "model_name" in src
