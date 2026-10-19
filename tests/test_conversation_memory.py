"""Memoria de conversación y lectura de URLs: bugs vistos usando la aplicación."""
import asyncio
import logging
import re
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


# ── El historial no llegaba al backend ─────────────────────────────────────

def test_frontend_sends_the_conversation_history():
    """El bug: el historial se construía y se pasaba a openStream, pero sse.js
    NO lo incluía en el cuerpo de la petición. Se descartaba en silencio, así
    que un "búscalo, por favor" no tenía a qué referirse."""
    src = (ROOT / "frontend/src/services/sse.js").read_text(encoding="utf-8")
    # Debe enviarse en LOS DOS caminos: streaming y no-streaming
    cuerpos = re.findall(r"body:\s*JSON\.stringify\(\{(.*?)\}\)", src, re.S)
    assert len(cuerpos) >= 2, "no se encontraron ambos caminos"
    for i, cuerpo in enumerate(cuerpos[:2]):
        assert "conversation_history" in cuerpo, f"camino {i + 1} no envía el historial"


def test_history_reaches_the_prompt():
    from app.core import prompt_builder as pb
    hist = [
        {"role": "user", "content": "¿cuándo sale GTA 6 en PS5?"},
        {"role": "assistant", "content": "No hay fecha oficial anunciada."},
    ]
    p = pb.PromptParts(message="sí es oficial, búscalo por favor")
    asyncio.run(pb.add_history(p, hist, context_window=8))
    salida = p.render()
    assert "GTA 6" in salida, "el modelo no vería de qué se habla"
    assert salida.rstrip().endswith("búscalo por favor")


def test_history_is_capped_by_context_window():
    """Enviar toda la conversación agotaría el contexto del modelo."""
    from app.core import prompt_builder as pb
    largo = [{"role": "user", "content": f"mensaje {i}"} for i in range(40)]
    p = pb.PromptParts(message="actual")
    asyncio.run(pb.add_history(p, largo, context_window=4))
    assert p.history.count("Usuario:") <= 4


# ── URLs que no se pueden leer ─────────────────────────────────────────────

def test_unreadable_url_falls_back_to_search():
    """Muchos sitios bloquean peticiones automáticas. Sin respaldo ni aviso, el
    modelo improvisaba y llegó a repetir mensajes internos de herramientas."""
    import inspect
    from app.core import prompt_builder as chat
    src = inspect.getsource(chat)
    assert "no se ha podido leer" in src
    assert "urlparse" in src, "no busca por el dominio como respaldo"


def test_model_told_not_to_leak_tool_internals():
    """Caso real: la respuesta explicaba 'start_index=10000' al usuario."""
    from app.specialists.identity import with_identity
    import os
    os.environ["ANDROMEDA_LANGUAGE"] = "en"
    out_en = with_identity("x", "generalist", "gemma3:27b", user_prompt="search this url")
    assert "NEVER explain your tools" in out_en
    os.environ["ANDROMEDA_LANGUAGE"] = "es"
    out_es = with_identity("x", "generalist", "gemma3:27b", user_prompt="busca esta url")
    assert "NUNCA expliques" in out_es


def test_url_is_still_detected_and_read():
    from app.core.web_search import extract_urls, needs_web_search
    p = "search it here https://www.rockstargames.com/VI"
    assert extract_urls(p) == ["https://www.rockstargames.com/VI"]
    assert needs_web_search(p) is True
