"""Fecha en el prompt, extracción de memoria y feedback: bugs vistos en uso real."""
import logging
from datetime import datetime

logging.disable(logging.CRITICAL)


# ── Fecha: el modelo respondía "15 de noviembre de 2023" ────────────────────

def test_date_is_at_the_very_start_of_the_prompt():
    """Enterrada al final de 3.500 caracteres, los modelos pequeños la ignoran."""
    from app.specialists.identity import with_identity
    out = with_identity("Eres útil.", "generalist", "gemma3:27b")
    head = out[:300].upper()
    assert "CURRENT DATE" in head or "FECHA ACTUAL" in head
    assert str(datetime.now().year) in out[:300]


def test_date_present_for_models_without_tool_support():
    """La rama que recorta capacidades no puede llevarse la fecha por delante."""
    from app.specialists.identity import with_identity
    for model in ("gemma3:27b", "llama3.2:1b", "qwen2.5:0.5b", ""):
        out = with_identity("x", "generalist", model)
        assert str(datetime.now().year) in out[:300], model


# ── Extractor: guardaba "it please" como si fuera un hecho ──────────────────

def test_trailing_remember_captures_the_fact_not_the_verb():
    """El bug real: 'X, remember it please' guardaba 'it please'."""
    from app.memory.extractor import extract_memories
    got = extract_memories("Nope, it is friday 4th of september 2026, remember it please")
    assert got, "no extrajo nada"
    content = got[0][0]
    assert "september" in content.lower()
    assert content.strip().lower() not in ("it please", "it", "please")


def test_trailing_remember_in_spanish():
    from app.memory.extractor import extract_memories
    got = extract_memories("mi cumpleaños es el 12 de marzo, recuérdalo")
    assert got and "marzo" in got[0][0]


def test_bare_remember_stores_nothing():
    """Sin contenido no hay nada que guardar: mejor vacío que basura."""
    from app.memory.extractor import extract_memories
    for msg in ("remember it please", "recuérdalo", "recuerda esto", "note this"):
        assert extract_memories(msg) == [], msg


def test_classic_remember_still_works():
    from app.memory.extractor import extract_memories
    got = extract_memories("recuerda que hoy es viernes")
    assert got and "viernes" in got[0][0]


def test_normal_patterns_unaffected():
    from app.memory.extractor import extract_memories
    assert extract_memories("me llamo Pau")[0][2] == "nombre"


# ── Memoria: persistencia real ──────────────────────────────────────────────

def test_profile_persists_across_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        c.put("/api/memory/profile", json={"text": "Me llamo Pau y vivo en Badalona."})
        assert "Badalona" in c.get("/api/memory/profile").json()["manual"]


# ── Feedback: los votos deben contar ───────────────────────────────────────

def test_feedback_votes_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        before = c.get("/api/feedback").json()
        assert c.post("/api/feedback", json={"request_id": "a", "positive": True}).json()["success"]
        assert c.post("/api/feedback", json={"request_id": "b", "positive": False}).json()["success"]
        after = c.get("/api/feedback").json()
        assert after["up"] == before["up"] + 1
        assert after["down"] == before["down"] + 1


# ── Búsqueda web activa por defecto, salvo incógnito ───────────────────────

def test_web_search_on_by_default():
    """Una IA que no puede consultar nada actual es una IA rota por defecto."""
    from app.core.flags import _DEFAULTS
    assert _DEFAULTS["andromeda_network_egress"] is True


def test_incognito_blocks_web_regardless_of_flag():
    """Incógnito es una garantía: no puede depender de un flag de ajustes."""
    import inspect
    from app.core import prompt_builder as chat
    src = inspect.getsource(chat)
    assert "not incognito and web_search" in src
