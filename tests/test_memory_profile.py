"""Tests del perfil de memoria unificado (estilo Claude)."""
import sys, tempfile, os
sys.path.insert(0, "backend")
from app.memory.profile import MemoryProfile


def _tmp():
    return MemoryProfile(tempfile.mktemp(suffix=".json"))


def test_upsert_replaces_same_topic():
    p = _tmp()
    p.upsert_fact("idioma", "Prefiere catalán")
    p.upsert_fact("idioma", "Prefiere inglés")
    txt = p.render()
    assert "inglés" in txt.lower()
    assert "catalán" not in txt.lower()  # reemplazado, no acumulado


def test_language_in_manual_is_cleaned_on_upsert():
    # Caso real de Pau: alemán escrito a mano, catalán desde el chat.
    p = _tmp()
    p.set_manual("Prefiero hablar en alemán.")
    p.upsert_fact("idioma", "Prefiere que le hablen en catalán")
    txt = p.render().lower()
    assert "catalán" in txt
    assert "alemán" not in txt


def test_render_is_cohesive_text_not_list():
    p = _tmp()
    p.upsert_fact("nombre", "Se llama Pau")
    p.upsert_fact("stack", "Trabaja con Python")
    txt = p.render()
    # Sin viñetas ni guiones de lista: es prosa.
    assert "- " not in txt
    assert "Pau" in txt and "Python" in txt


def test_manual_edit_persists():
    p = _tmp()
    p.set_manual("Le gusta el café.")
    assert "café" in p.get()["text"]


def test_clear_empties_profile():
    p = _tmp()
    p.upsert_fact("nombre", "Pau")
    p.clear()
    assert p.get()["is_empty"] is True


def test_delete_fact():
    p = _tmp()
    p.upsert_fact("nombre", "Pau")
    p.upsert_fact("stack", "Rust")
    assert p.delete_fact("stack") is True
    assert "rust" not in p.render().lower()
    assert "pau" in p.render().lower()


def test_memory_profile_initialized_in_app(tmp_path, monkeypatch):
    """Regresión: app.state.memory_profile debe existir tras el startup.

    Sin esto, PUT /api/memory/profile devolvía 503 ('No se pudo guardar' en la
    UI) y el auto-guardado del extractor no hacía nada en silencio.
    """
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    app = create_app()
    with TestClient(app) as c:
        r = c.put('/api/memory/profile', json={'text': 'test de memoria'})
        assert r.status_code == 200, "PUT del perfil debe funcionar (antes: 503)"
        r = c.get('/api/memory/profile')
        assert 'test de memoria' in (r.json().get('text') or '')
