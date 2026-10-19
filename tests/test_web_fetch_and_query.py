"""Lectura de URLs pegadas y limpieza de la consulta de búsqueda."""
import asyncio
import logging

logging.disable(logging.CRITICAL)


# ── Limpieza de la consulta ────────────────────────────────────────────────

def test_query_drops_the_request_words():
    """Buscar 'busca en internet X' devuelve páginas sobre buscar, no sobre X."""
    from app.core.web_search import clean_query
    q = clean_query("Busca en internet el resultado entre real betis y real madrid de hoy")
    assert "busca" not in q.lower()
    assert "internet" not in q.lower()
    assert "betis" in q.lower() and "madrid" in q.lower()


def test_query_keeps_short_prompts_intact():
    from app.core.web_search import clean_query
    assert clean_query("cuanto vale el gta 6") == "cuanto vale el gta 6"


def test_query_never_becomes_empty():
    """Si al limpiar no queda nada, es mejor buscar el texto original."""
    from app.core.web_search import clean_query
    for q in ("busca", "search", "por favor"):
        assert clean_query(q).strip(), q


# ── URLs pegadas por el usuario ────────────────────────────────────────────

def test_extracts_url_from_message():
    from app.core.web_search import extract_urls
    urls = extract_urls("esta es la url del resultado: https://www.marca.com/futbol/x.html")
    assert urls == ["https://www.marca.com/futbol/x.html"]


def test_search_engine_url_becomes_a_query():
    """Leer una página de resultados de Google da el HTML del buscador, no datos."""
    from app.core.web_search import search_terms_from_url
    url = ("https://www.google.com/search?client=opera&q=real+madrid+betis"
           "&sourceid=opera&ie=UTF-8&oe=UTF-8")
    assert search_terms_from_url(url) == "real madrid betis"


def test_normal_url_is_not_treated_as_a_query():
    from app.core.web_search import search_terms_from_url
    assert search_terms_from_url("https://www.marca.com/futbol/resultado.html") == ""


def test_fetch_url_rejects_non_http():
    from app.core.web_search import fetch_url
    for bad in ("file:///etc/passwd", "ftp://x.com", "javascript:alert(1)", ""):
        assert asyncio.run(fetch_url(bad)) is None, bad


def test_fetch_url_returns_none_on_failure():
    """Sin red debe devolver None, nunca lanzar: el chat no puede romperse."""
    from app.core.web_search import fetch_url
    assert asyncio.run(fetch_url("http://127.0.0.1:1/nada", timeout=1.0)) is None


def test_chat_reads_pasted_urls():
    """Antes dependía de que el modelo supiera usar la herramienta MCP fetch."""
    import inspect
    from app.core import prompt_builder as chat
    src = inspect.getsource(chat)
    assert "extract_urls" in src and "fetch_url" in src
    assert "search_terms_from_url" in src
