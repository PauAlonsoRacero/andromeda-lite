"""El constructor de prompts: qué recibe realmente el modelo.

Esta es la pieza que no tenía tests y donde han aparecido casi todos los bugs
encontrados usando la aplicación (la fecha inventada, la memoria desconectada,
avisos que se pisaban entre sí).
"""
import asyncio
import logging

logging.disable(logging.CRITICAL)


# ── Orden y ensamblado ─────────────────────────────────────────────────────

def test_message_alone_is_untouched():
    from app.core.prompt_builder import PromptParts
    p = PromptParts(message="hola")
    assert p.render() == "hola"


def test_user_message_always_goes_last():
    """Es la posición a la que más atención prestan los modelos."""
    from app.core.prompt_builder import PromptParts
    p = PromptParts(message="MI PREGUNTA")
    p.skill = "instrucciones de skill"
    p.documents = "documentos"
    p.history = "historial"
    out = p.render()
    assert out.rstrip().endswith("MI PREGUNTA")


def test_block_order_is_deterministic():
    """Lo que condiciona CÓMO responder va antes que los datos."""
    from app.core.prompt_builder import PromptParts
    p = PromptParts(message="m")
    p.notice, p.skill, p.memory = "AVISO", "SKILL", "MEMORIA"
    p.documents, p.web, p.history = "DOCS", "WEB", "HIST"
    out = p.render()
    posiciones = [out.index(x) for x in
                  ("AVISO", "SKILL", "MEMORIA", "DOCS", "WEB", "HIST")]
    assert posiciones == sorted(posiciones), "el orden de los bloques cambió"


def test_notices_accumulate_instead_of_overwriting():
    """El bug: cada aviso pisaba al anterior y solo llegaba uno al modelo."""
    from app.core.prompt_builder import PromptParts, add_notice
    p = PromptParts(message="m")
    add_notice(p, "primer aviso")
    add_notice(p, "segundo aviso")
    assert "primer aviso" in p.notice and "segundo aviso" in p.notice


def test_empty_blocks_leave_no_separators():
    from app.core.prompt_builder import PromptParts
    p = PromptParts(message="m")
    p.skill = "solo skill"
    out = p.render()
    assert "\n\n\n" not in out


# ── Incógnito: la garantía más importante ─────────────────────────────────

def test_incognito_skips_memory():
    from app.core.prompt_builder import PromptParts, add_memory_async

    class Perfil:
        def render(self):
            return "DATOS PRIVADOS DEL USUARIO"

    p = PromptParts(message="m")
    asyncio.run(add_memory_async(p, "hola", Perfil(), None, incognito=True))
    assert p.memory == "", "el perfil se filtró en modo incógnito"


def test_incognito_skips_documents_and_workspace():
    from app.core.prompt_builder import PromptParts, add_documents, add_workspace

    class Indice:
        def query(self, q, k=3):
            return [{"doc_id": "secreto.md", "text": "contenido privado"}]

    p = PromptParts(message="m")
    add_documents(p, "consulta", Indice(), incognito=True)
    add_workspace(p, "modifica el archivo html", incognito=True)
    assert p.documents == ""


def test_normal_mode_does_include_memory():
    """No vaciar la funcionalidad por el camino."""
    from app.core.prompt_builder import PromptParts, add_memory_async

    class Perfil:
        def render(self):
            return "El usuario se llama Pau"

    p = PromptParts(message="m")
    asyncio.run(add_memory_async(p, "hola", Perfil(), None, incognito=False))
    assert "Pau" in p.memory


# ── Robustez: un componente roto no puede tumbar el chat ──────────────────

def test_broken_components_do_not_break_the_chat():
    from app.core.prompt_builder import (
        PromptParts, add_documents, add_memory_async, add_skill,
    )

    class Roto:
        def match(self, *a, **k):
            raise RuntimeError("skill rota")

        def query(self, *a, **k):
            raise RuntimeError("rag roto")

        def render(self):
            raise RuntimeError("perfil roto")

    p = PromptParts(message="mi pregunta")
    add_skill(p, "x", Roto())
    add_documents(p, "x", Roto(), incognito=False)
    asyncio.run(add_memory_async(p, "x", Roto(), None, incognito=False))
    assert p.render() == "mi pregunta"     # degrada, no revienta


def test_none_components_are_safe():
    from app.core.prompt_builder import (
        PromptParts, add_documents, add_memory_async, add_skill, add_workspace,
    )
    p = PromptParts(message="m")
    add_skill(p, "x", None)
    add_documents(p, "x", None, incognito=False)
    add_workspace(p, "x", incognito=False)
    asyncio.run(add_memory_async(p, "x", None, None, incognito=False))
    assert p.render() == "m"


# ── Contenido de cada bloque ──────────────────────────────────────────────

def test_skill_is_activated_and_reported():
    from app.core.prompt_builder import PromptParts, add_skill

    class Skill:
        name, body = "Code Review", "Revisa el código."

    class Reg:
        def match(self, q, k=1):
            return [Skill()]

    p = PromptParts(message="revisa esto")
    add_skill(p, "revisa esto", Reg())
    assert "Code Review" in p.skill
    assert p.meta["skill_used"] == "Code Review"   # la UI lo muestra


def test_documents_are_cited_by_id():
    from app.core.prompt_builder import PromptParts, add_documents

    class Indice:
        def query(self, q, k=3):
            return [{"doc_id": "manual.md", "text": "el puerto es 8765"}]

    p = PromptParts(message="qué puerto")
    add_documents(p, "qué puerto", Indice(), incognito=False)
    assert "[manual.md]" in p.documents
    assert p.meta["rag_sources"] == ["manual.md"]


def test_web_results_are_numbered_and_flagged():
    from app.core.prompt_builder import PromptParts, add_web_results
    p = PromptParts(message="precio")
    add_web_results(p, [{"title": "T", "snippet": "S", "url": "https://x"}])
    assert "[1]" in p.web and p.meta["web_used"] is True


def test_history_is_compacted_when_too_long():
    """La compactación solo existía en un camino: en streaming se truncaba."""
    from app.core.prompt_builder import PromptParts, add_history
    largo = [{"role": "user", "content": "palabra " * 80} for _ in range(20)]
    largo.append({"role": "user", "content": "ULTIMO MENSAJE"})
    p = PromptParts(message="m")
    asyncio.run(add_history(p, largo, context_window=4))
    assert "ULTIMO MENSAJE" in p.history
    assert p.meta.get("context_compacted") is True


def test_slash_command_expands_before_everything():
    from app.core.prompt_builder import expand_slash
    assert len(expand_slash("/explain qué es un mutex")) > 40
    assert expand_slash("texto normal") == "texto normal"


# ── Coexistencia: el bug que resolvió la unificación ──────────────────────

def test_all_blocks_coexist_without_overwriting():
    """El bug original: cada bloque reasignaba la variable del prompt y tiraba
    el trabajo anterior. Una búsqueda web borraba la skill, el RAG y la memoria.
    """
    from app.core.prompt_builder import (
        PromptParts, add_documents, add_notice, add_skill, add_web_results,
    )

    class Skill:
        name, body = "Code Review", "Revisa el código."

    class Reg:
        def match(self, q, k=1):
            return [Skill()]

    class Indice:
        def query(self, q, k=3):
            return [{"doc_id": "manual.md", "text": "el puerto es 8765"}]

    p = PromptParts(message="MI PREGUNTA")
    add_skill(p, "revisa", Reg())
    add_documents(p, "puerto", Indice(), incognito=False)
    add_web_results(p, [{"title": "T", "snippet": "S", "url": "https://x"}])
    add_notice(p, "UN AVISO")

    out = p.render()
    # Las cuatro piezas deben seguir ahí
    assert "Code Review" in out
    assert "manual.md" in out
    assert "https://x" in out
    assert "UN AVISO" in out
    assert out.rstrip().endswith("MI PREGUNTA")


def test_both_chat_paths_use_the_shared_builder():
    """Streaming y no-streaming deben construir el prompt igual.

    Estaban duplicados y se desincronizaron: la compactación y el perfil de
    memoria solo existían en uno de los dos.
    """
    import inspect
    from app.core import router
    from app.routes import chat
    for mod, nombre in ((chat, "chat.py"), (router, "router.py")):
        src = inspect.getsource(mod)
        assert "prompt_builder" in src, f"{nombre} no usa el constructor compartido"
        assert "add_history" in src, f"{nombre} no compacta el historial"
        assert "add_memory_async" in src, f"{nombre} no consulta la memoria"
