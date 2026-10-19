"""Las capacidades básicas deben funcionar de fábrica, sin configurar nada.

Como en Claude: internet, memoria y creación de archivos vienen activados, no
dependen de instalar un conector, y funcionan desde el primer mensaje.
"""
import asyncio
import logging
import os
import tempfile

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Todo activo de fábrica ─────────────────────────────────────────────────

def test_core_capabilities_are_on_by_default(tmp_path, monkeypatch):
    from app.core.flags import get_flag
    with _client(tmp_path, monkeypatch) as c:
        st = c.app.state
        assert get_flag(st.settings, "andromeda_network_egress"), "internet apagado"
        assert get_flag(st.settings, "andromeda_file_creation"), "archivos apagado"
        assert st.memory_store is not None, "memoria semántica sin inicializar"
        assert st.memory_profile is not None, "perfil de memoria sin inicializar"
        assert st.rag_index is not None, "documentos sin inicializar"
        assert st.skill_registry is not None, "skills sin inicializar"


def test_web_search_does_not_depend_on_mcp():
    """La búsqueda es propia de Andromeda: no puede exigir instalar un conector."""
    import inspect
    from app.core import web_search
    src = inspect.getsource(web_search.search_web)
    assert "mcp" not in src.lower()


# ── Internet: detectar cuándo hace falta, en ambos idiomas ────────────────

def test_current_info_questions_trigger_search_in_english():
    """La heurística estaba sesgada al español: "when is X launching" o
    "who won X" no buscaban, y el modelo respondía de memoria."""
    from app.core.web_search import needs_web_search
    for p in ("when is gta 6 launching on ps5?", "when does gta 6 release",
              "is gta 6 out yet", "who won the world cup",
              "how much is an iphone", "latest version of python"):
        assert needs_web_search(p), f"no buscaría: {p!r}"


def test_current_info_questions_trigger_search_in_spanish():
    from app.core.web_search import needs_web_search
    for p in ("cuándo sale gta 6", "quién ganó el mundial",
              "cuánto vale el bitcoin", "últimas noticias"):
        assert needs_web_search(p), f"no buscaría: {p!r}"


def test_timeless_questions_do_not_search():
    from app.core.web_search import needs_web_search
    for p in ("explain pointers in C", "write me a poem", "what is recursion",
              "hello how are you", "explícame la recursividad"):
        assert not needs_web_search(p), f"buscaría de más: {p!r}"


# ── Memoria: dentro del chat y entre sesiones ────────────────────────────

def test_the_model_sees_the_previous_turns():
    """El fallo real: "yes it is official, search it please" no tenía a qué
    referirse porque el historial nunca llegaba al backend."""
    from app.core import prompt_builder as pb
    hist = [{"role": "user", "content": "when is gta 6 launching on ps5?"},
            {"role": "assistant", "content": "No official date yet."}]
    p = pb.PromptParts(message="yes it is official, search it please")
    asyncio.run(pb.add_history(p, hist, context_window=8))
    assert "gta 6" in p.render().lower()


def test_memories_persist_and_are_retrieved(tmp_path):
    from app.memory.store import SemanticMemoryStore
    st = SemanticMemoryStore(db_path=str(tmp_path / "m.db"),
                             ollama_url="http://127.0.0.1:1")
    asyncio.run(st.save("El proyecto de Pau se llama Andromeda",
                        source="chat", category="fact"))
    hits = asyncio.run(st.search("como se llama el proyecto", k=1))
    assert hits and "Andromeda" in hits[0]["content"]


# ── Creación de archivos ──────────────────────────────────────────────────

def test_file_creation_works_end_to_end(monkeypatch):
    """Del bloque que emite el modelo al archivo escrito en disco."""
    ws = tempfile.mkdtemp()
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", ws)
    from app.core.file_actions import execute_actions
    texto = 'Aquí tienes:\n\n```andromeda:write path="hola.txt"\ncontenido de prueba\n```\n'
    resultados = execute_actions(texto)
    assert resultados and resultados[0].ok
    destino = os.path.join(ws, "hola.txt")
    assert os.path.exists(destino)
    assert open(destino).read().strip() == "contenido de prueba"


def test_file_instructions_reach_the_model():
    from app.specialists.identity import with_identity
    out = with_identity("x", "generalist", "gemma3:27b",
                        user_prompt="crea un archivo index.html")
    assert "andromeda:write" in out


def test_workspace_exists_on_startup(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch):
        ws = os.environ.get("ANDROMEDA_WORKSPACE", "")
        assert ws and os.path.isdir(ws), "el workspace no se crea al arrancar"
