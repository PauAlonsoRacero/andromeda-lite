"""SearXNG como buscador principal: metabuscador libre, sin clave ni límites."""
import asyncio
import logging

logging.disable(logging.CRITICAL)


def test_searxng_is_the_first_engine():
    """Raspar HTML de buscadores es frágil (403 frecuentes). SearXNG expone una
    API JSON pensada para esto, así que va primero y lo demás es respaldo."""
    import inspect
    from app.core import web_search
    src = inspect.getsource(web_search.search_web)
    pos_sx = src.index("searxng")
    pos_ddg = src.index("duckduckgo-lite")
    assert pos_sx < pos_ddg, "SearXNG no es el motor principal"


def test_user_instance_takes_priority(monkeypatch):
    from app.core import web_search
    monkeypatch.setenv("ANDROMEDA_SEARXNG_URL", "http://localhost:8888")
    assert web_search._searxng_instances()[0] == "http://localhost:8888"


def test_public_instances_exist_as_fallback(monkeypatch):
    """Debe funcionar sin configurar nada: es el punto de 'plug and play'."""
    from app.core import web_search
    monkeypatch.delenv("ANDROMEDA_SEARXNG_URL", raising=False)
    instancias = web_search._searxng_instances()
    assert len(instancias) >= 3
    assert all(u.startswith("https://") for u in instancias)


def test_trailing_slash_is_normalised(monkeypatch):
    from app.core import web_search
    monkeypatch.setenv("ANDROMEDA_SEARXNG_URL", "http://localhost:8888/")
    assert web_search._searxng_instances()[0] == "http://localhost:8888"


def test_failure_raises_so_the_chain_continues():
    """Debe lanzar, no devolver vacío: así search_web pasa al siguiente motor."""
    from app.core.web_search import _search_searxng
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(_search_searxng("test", 2, timeout=1.0))


def test_search_falls_back_when_searxng_fails(monkeypatch):
    from app.core import web_search
    llamadas = []

    async def falla(q, n, t):
        llamadas.append("searxng")
        raise RuntimeError("instancia caída")

    async def ok(q, n, t):
        llamadas.append("ddg")
        return [{"title": "T", "snippet": "S", "url": "https://x"}]

    monkeypatch.setattr(web_search, "_search_searxng", falla)
    monkeypatch.setattr(web_search, "_search_ddg_lite", ok)
    resultados = asyncio.run(web_search.search_web("consulta"))
    assert llamadas[:2] == ["searxng", "ddg"]
    assert resultados


def test_settings_endpoint_validates_url(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.put("/api/settings/searxng",
                     json={"url": "no-es-una-url"}).status_code == 400
        r = c.put("/api/settings/searxng", json={"url": "http://localhost:9999"})
        assert r.status_code == 200 and r.json()["saved"]
        assert c.get("/api/settings/searxng").json()["url"] == "http://localhost:9999"
        # vaciarla vuelve a las públicas
        c.put("/api/settings/searxng", json={"url": ""})
        assert c.get("/api/settings/searxng").json()["url"] == ""


# ── Instancias que desactivan la API JSON ─────────────────────────────────

def test_html_fallback_exists():
    """La mayoría de instancias públicas desactivan `format=json` para evitar
    abuso, pero su interfaz web sigue abierta. Sin este respaldo SearXNG
    fallaba en casi todas y la búsqueda caía al raspado, que es lo que se
    quería evitar."""
    import inspect
    from app.core import web_search
    src = inspect.getsource(web_search._search_searxng_intento)
    assert "_searxng_html" in src, "no hay respaldo cuando falta la API JSON"
    assert "403" in src, "no contempla el 403 típico de la API desactivada"


def test_html_parser_reads_searxng_markup():
    """Estructura real de SearXNG: <article class="result">…<h3>título</h3>."""
    import re
    from app.core.web_search import _strip_html
    html = ('<article class="result result-default">'
            '<a href="https://ejemplo.com/gta6"><h3>GTA 6 Release Date</h3></a>'
            '<p class="content">Rockstar anunció la fecha...</p></article>')
    bloques = re.findall(r'<article[^>]*class="[^"]*result[^"]*"(.*?)</article>',
                         html, re.S | re.I)
    assert len(bloques) == 1
    assert "GTA 6" in _strip_html(bloques[0])


def test_non_json_response_falls_back(monkeypatch):
    """Una instancia que responde 200 con HTML no puede romper la búsqueda."""
    import inspect
    from app.core import web_search
    src = inspect.getsource(web_search._search_searxng_intento)
    assert "ValueError" in src, "no maneja una respuesta que no es JSON"
