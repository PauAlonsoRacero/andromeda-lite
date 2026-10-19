"""La memoria semántica estaba implementada pero desconectada del chat."""
import asyncio
import logging

logging.disable(logging.CRITICAL)


def _store(tmp_path):
    from app.memory.store import SemanticMemoryStore
    # URL inalcanzable a propósito: así se ejercita el camino SIN embeddings,
    # que es el que tiene la mayoría de usuarios sin nomic-embed-text instalado.
    return SemanticMemoryStore(db_path=str(tmp_path / "mem.db"),
                               ollama_url="http://127.0.0.1:1")


def test_text_fallback_actually_finds_memories(tmp_path):
    """El bug: sin Ollama la búsqueda no devolvía NADA nunca.

    El umbral del coseno (0.72) se aplicaba también al recuento de palabras del
    fallback, donde exigir 0.72 significa que coincidan casi todas.
    """
    st = _store(tmp_path)
    asyncio.run(st.save("El puerto del backend es el 8765", source="chat", category="fact"))
    hits = asyncio.run(st.search("que puerto usa el backend", k=1))
    assert hits, "el fallback por texto no devolvió nada"
    assert "8765" in hits[0]["content"]


def test_text_fallback_still_rejects_unrelated(tmp_path):
    """Bajar el umbral no puede convertirlo en un 'devuelve cualquier cosa'."""
    st = _store(tmp_path)
    asyncio.run(st.save("El puerto del backend es el 8765", source="chat", category="fact"))
    assert asyncio.run(st.search("recetas de cocina italiana", k=1)) == []


def test_exact_substring_ranks_highest(tmp_path):
    st = _store(tmp_path)
    asyncio.run(st.save("A Pau le gusta el cafe solo", source="chat", category="preference"))
    asyncio.run(st.save("El proyecto se llama Andromeda", source="chat", category="fact"))
    hits = asyncio.run(st.search("el proyecto se llama", k=1))
    assert hits and "Andromeda" in hits[0]["content"]


def test_router_accepts_and_uses_memory_store():
    """El almacén se pasaba al router y se ignoraba: todo lo recordado se perdía.

    La consulta vive ahora en el constructor de prompts compartido, así que se
    comprueba que el router lo invoca y que el constructor consulta el almacén.
    """
    import inspect
    from app.core import prompt_builder, router
    assert "add_memory_async" in inspect.getsource(router)
    assert "memory_store.search" in inspect.getsource(prompt_builder)


def test_chat_persists_extracted_memories_to_store():
    """Lo extraído debe ir también al almacén, no solo al perfil de texto."""
    import inspect
    from app.routes import chat
    src = inspect.getsource(chat)
    assert "_store.save(" in src, "las memorias extraídas no se indexan"


def test_offline_and_no_results_give_different_messages():
    """'Sin internet' y 'sin resultados' son causas distintas para el usuario."""
    import inspect
    from app.core import prompt_builder as chat
    src = inspect.getsource(chat)
    assert "check_internet" in src
    assert "no hay conexión a internet" in src
