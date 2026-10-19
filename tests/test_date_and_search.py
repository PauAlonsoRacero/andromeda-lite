"""Fecha real en el prompt y búsqueda web con motores de respaldo."""
import asyncio
from datetime import datetime

import pytest


# ── Fecha actual ────────────────────────────────────────────────────────────

def test_identity_includes_real_current_date(monkeypatch):
    """El fallo original: el modelo respondía con la fecha de su entrenamiento."""
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "es")
    from app.specialists.identity import with_identity
    out = with_identity("Eres un asistente.", "generalist", "")
    now = datetime.now()
    assert "FECHA ACTUAL" in out
    assert str(now.year) in out
    assert str(now.day) in out


def test_identity_date_in_english(monkeypatch):
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "en")
    from app.specialists.identity import with_identity
    out = with_identity("You are an assistant.", "generalist", "")
    assert "CURRENT DATE" in out
    assert str(datetime.now().year) in out


def test_identity_tells_model_not_to_use_training_cutoff(monkeypatch):
    """Debe instruir explícitamente a no deducir la fecha del entrenamiento."""
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "es")
    from app.specialists.identity import with_identity
    out = with_identity("x", "generalist", "").lower()
    assert "corte" in out or "cutoff" in out


# ── Búsqueda web ────────────────────────────────────────────────────────────

def test_needs_web_search_detects_current_info_questions():
    from app.core.web_search import needs_web_search
    for q in ["cuanto vale el gta 6", "búscalo por internet", "últimas noticias",
              "quién ganó el mundial", "search for the current price"]:
        assert needs_web_search(q) is True, q


def test_needs_web_search_ignores_timeless_questions():
    from app.core.web_search import needs_web_search
    for q in ["explícame la recursividad", "escribe una función en python"]:
        assert needs_web_search(q) is False, q


def test_search_falls_back_across_engines(monkeypatch):
    """Si un motor falla, debe probarse el siguiente en vez de rendirse."""
    from app.core import web_search
    calls = []

    async def fail(q, n, t):
        calls.append("ddg_lite")
        raise RuntimeError("HTTP 403")

    async def fail2(q, n, t):
        calls.append("ddg_html")
        return []

    async def ok(q, n, t):
        calls.append("wikipedia")
        return [{"title": "GTA VI", "snippet": "videojuego", "url": "https://x"}]

    monkeypatch.setattr(web_search, "_search_ddg_lite", fail)
    monkeypatch.setattr(web_search, "_search_ddg_html", fail2)
    monkeypatch.setattr(web_search, "_search_wikipedia", ok)
    results = asyncio.run(web_search.search_web("gta 6"))
    assert len(calls) == 3, calls          # recorre todos hasta encontrar uno
    assert calls[-1] == "wikipedia"
    assert results and results[0]["title"] == "GTA VI"


def test_search_returns_empty_when_all_engines_fail(monkeypatch):
    """Sin resultados debe devolver lista vacía, nunca lanzar excepción."""
    from app.core import web_search

    async def boom(q, n, t):
        raise RuntimeError("sin red")

    for name in ("_search_ddg_html", "_search_ddg_lite", "_search_wikipedia"):
        monkeypatch.setattr(web_search, name, boom)
    assert asyncio.run(web_search.search_web("lo que sea")) == []


def test_ddg_lite_parser_extracts_results():
    from app.core.web_search import _parse_ddg_lite
    html = ('<a class="result-link" href="https://a.com">Primer resultado</a>'
            '<td class="result-snippet">Un resumen del primero</td>'
            '<a class="result-link" href="https://b.com">Segundo</a>'
            '<td class="result-snippet">Otro resumen</td>')
    out = _parse_ddg_lite(html, 5)
    assert len(out) == 2
    assert out[0]["title"] == "Primer resultado"
    assert out[0]["url"] == "https://a.com"
    assert "resumen" in out[0]["snippet"]


def test_network_egress_flag_defaults_on():
    """Decisión revisada: una IA que no puede consultar nada actual está rota
    de fábrica. La red va activa por defecto y el modo incógnito la corta."""
    from app.core.flags import _DEFAULTS
    assert _DEFAULTS["andromeda_network_egress"] is True



def test_time_is_present_at_the_end():
    """La hora sigue en el prompt, pero al final (caché de prefijo de Ollama)."""
    import os
    from app.specialists.identity import with_identity
    os.environ["ANDROMEDA_LANGUAGE"] = "es"
    s = with_identity("x", "generalist", "qwen3:8b", user_prompt="hola")
    assert "HORA ACTUAL:" in s and s.rstrip().splitlines()[-1].startswith("HORA ACTUAL:")
