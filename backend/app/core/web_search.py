"""
web_search.py — Búsqueda web para Andromeda.

Cuando el chat NO está en modo incógnito, Andromeda puede buscar en internet
para enriquecer las respuestas con información actualizada.
En modo incógnito, esta función NUNCA se llama — Andromeda funciona 100% local.

Usa DuckDuckGo (sin API key, sin tracking) como motor de búsqueda.
"""
import logging

import httpx

logger = logging.getLogger("andromeda.web_search")

DDG_HTML = "https://html.duckduckgo.com/html/"


async def search_web(query: str, max_results: int = 5, timeout: float = 8.0) -> list[dict]:
    """
    Busca en internet y retorna una lista de resultados.

    Returns:
        [{"title": str, "snippet": str, "url": str}, ...]
        Lista vacía si falla o no hay conexión.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                DDG_HTML,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Andromeda)"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                return []
            return _parse_ddg_html(resp.text, max_results)
    except Exception as exc:
        logger.warning(f"Búsqueda web falló: {exc}")
        return []


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Extrae resultados del HTML de DuckDuckGo (sin dependencias externas)."""
    import re
    results = []
    # Bloques de resultado
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>)?',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        url = m.group(1)
        title = _strip_html(m.group(2) or "")
        snippet = _strip_html(m.group(3) or "")
        if title and url:
            results.append({"title": title, "snippet": snippet, "url": url})
        if len(results) >= max_results:
            break
    return results


def _strip_html(s: str) -> str:
    import re
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return s.strip()


async def check_internet(timeout: float = 3.0) -> bool:
    """Comprueba si hay conexión a internet."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://duckduckgo.com", timeout=timeout)
            return r.status_code == 200
    except Exception:
        return False


def needs_web_search(prompt: str) -> bool:
    """
    Heurística: ¿este prompt se beneficiaría de buscar en internet?

    Detecta preguntas sobre actualidad, datos que cambian, eventos, deportes,
    personas, lugares y cualquier hecho que un modelo local no puede saber con
    fiabilidad (y que tiende a alucinar). Mejor pecar de buscar de más en
    preguntas factuales que dejar al modelo inventar.
    """
    import unicodedata as _ud
    p = "".join(c for c in _ud.normalize("NFD", prompt.lower())
                if _ud.category(c) != "Mn")

    # Triggers explícitos de actualidad / petición de búsqueda
    triggers = [
        "ultimo", "ultima", "reciente", "actual", "ahora", "hoy", "ayer",
        "2023", "2024", "2025", "2026", "este ano", "este mes",
        "noticia", "precio", "cotizacion", "cuanto cuesta", "cuanto vale",
        "latest", "current", "news", "price", "today", "recent",
        "busca", "search", "internet", "web", "google", "en linea",
        # Eventos y resultados (lo que falló con el mundial)
        "mundial", "champions", "liga", "partido", "resultado", "marcador",
        "gano", "ganador", "campeon", "clasificacion", "posicion",
        "elecciones", "presidente", "ministro", "premio", "oscar",
        # Preguntas sobre entidades cambiantes
        "quien es", "quien gano", "quien es el", "como ha quedado",
        "como quedo", "que paso con", "que paso en", "estado de",
        "version de", "cuando sale", "cuando es", "fecha de",
    ]
    if any(t in p for t in triggers):
        return True

    # Preguntas factuales sobre personas/lugares/organizaciones concretas:
    # patrón "¿quién/qué/cuándo/dónde ... [Nombre Propio]?" suele necesitar datos
    # frescos. Si hay un nombre propio (palabra capitalizada que no es la primera)
    # junto a una palabra interrogativa, buscamos.
    import re as _re
    has_question = any(w in p for w in ("quien", "que ", "cuando", "donde", "cuanto", "cual"))
    proper_nouns = _re.findall(r"(?<!^)(?<![.!?]\s)\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}", prompt)
    if has_question and len(proper_nouns) >= 1:
        return True

    return False
