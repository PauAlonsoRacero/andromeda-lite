"""
web_search.py — Búsqueda web para Andromeda.

Cuando el chat NO está en modo incógnito, Andromeda puede buscar en internet
para enriquecer las respuestas con información actualizada.
En modo incógnito, esta función NUNCA se llama — Andromeda funciona 100% local.

Usa DuckDuckGo (sin API key, sin tracking) como motor de búsqueda.
"""
import logging
import re

import httpx

logger = logging.getLogger("andromeda.web_search")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:
        @staticmethod
        def log(*a, **k): pass
    diag = _Nulo()

DDG_HTML = "https://html.duckduckgo.com/html/"



# Palabras con las que el usuario PIDE la búsqueda, pero que no forman parte de
# lo que quiere encontrar. Buscar "busca en internet el resultado de X" devuelve
# páginas sobre buscar en internet, no sobre X.
_QUERY_NOISE = re.compile(
    r"\b(busca(me)?|buscar|búscame|search|look up|google|find|"
    r"por ?favor|please|en internet|on the internet|en la web|online|"
    r"puedes|could you|can you|dime|tell me|necesito saber|quiero saber)\b",
    re.IGNORECASE,
)


def clean_query(prompt: str) -> str:
    """Extrae los términos buscables de una petición en lenguaje natural."""
    q = _QUERY_NOISE.sub(" ", prompt or "")
    q = re.sub(r"[¿?¡!\"']", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" .,:;-")
    # Si al limpiar no queda casi nada, es mejor buscar el texto original.
    return q if len(q) >= 4 else (prompt or "").strip()



def _limpiar_resultados(resultados: list[dict] | None) -> list[dict]:
    """Quita anuncios y deshace las URLs de redirección.

    En un registro real, dos de cada cuatro "resultados" eran anuncios
    (duckduckgo.com/y.js?ad_domain=…) con URLs de más de 2.000 caracteres:
    ocupaban contexto y empujaban al modelo a responder con publicidad.
    Se piden unos cuantos resultados de más para compensar los descartados.
    """
    from urllib.parse import parse_qs, unquote, urlparse
    limpios, vistos = [], set()
    for r in resultados or []:
        url = (r.get("url") or "").replace("&amp;", "&")
        if "y.js" in url or "ad_domain=" in url or "ad_provider=" in url or "/aclick" in url:
            continue
        # //duckduckgo.com/l/?uddg=<url real>
        if "duckduckgo.com/l/" in url:
            real = parse_qs(urlparse(url if url.startswith("http") else "https:" + url).query).get("uddg")
            if real:
                url = unquote(real[0])
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http") or url in vistos:
            continue
        vistos.add(url)
        limpios.append({**r, "url": url})
    return limpios

async def search_web(query: str, max_results: int = 5, timeout: float = 8.0) -> list[dict]:
    """
    Busca en internet y devuelve una lista de resultados.

    Se prueban varios motores en orden. Un único proveedor es un punto de
    fallo: DuckDuckGo cambia su HTML o responde 403 según la red desde la que
    se consulte, y cuando eso pasa el usuario ve a la IA decir "he buscado" con
    las manos vacías. Con respaldos, la búsqueda sigue funcionando.

    Returns:
        [{"title": str, "snippet": str, "url": str}, ...]
        Lista vacía solo si TODOS los motores fallan.
    """
    query = clean_query(query)
    # SearXNG va primero: es un metabuscador de código abierto con API JSON, sin
    # clave ni límites, que consulta a varios buscadores por ti desde su
    # servidor. Los métodos que raspan HTML quedan como respaldo porque los
    # buscadores devuelven 403 con frecuencia según la red desde la que llegue
    # la petición.
    engines = (
        ("searxng", _search_searxng),
        ("duckduckgo-lite", _search_ddg_lite),
        ("duckduckgo-html", _search_ddg_html),
        ("wikipedia", _search_wikipedia),
    )
    # El último motor que funcionó se prueba primero (salvo Wikipedia, que es el
    # último recurso). En los registros de Pau, DuckDuckGo Lite devolvía 0
    # resultados en todas las búsquedas (~1 s perdido) y el HTML sí funcionaba.
    global _ultimo_motor_ok
    if _ultimo_motor_ok and _ultimo_motor_ok != "wikipedia":
        engines = tuple(sorted(engines, key=lambda e: e[0] != _ultimo_motor_ok))
    diag.log("search", f"buscando: {query!r}",
             data={"motores": [n for n, _ in engines]})
    for name, fn in engines:
        try:
            import time as _t
            _t0 = _t.perf_counter()
            results = _limpiar_resultados(await fn(query, max_results + 3, timeout))[:max_results]
            _ms = (_t.perf_counter() - _t0) * 1000
            diag.log("search", f"motor {name}: {len(results or [])} resultados",
                     data={"motor": name, "resultados": len(results or [])},
                     duration_ms=_ms,
                     level="success" if results else "warn")
            if results:
                logger.info(f"Búsqueda web OK vía {name}: {len(results)} resultados")
                _ultimo_motor_ok = name
                return results
            logger.info(f"Búsqueda web sin resultados vía {name}; probando siguiente")
        except Exception as exc:
            logger.info(f"Motor {name} falló ({type(exc).__name__}); probando siguiente")
            diag.log("search", f"motor {name}: falló",
                     detail=f"{type(exc).__name__}: {exc}"[:300], level="warn")
    logger.warning(f"Ningún motor de búsqueda devolvió resultados para: {query!r}")
    return []


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# Instancias públicas de SearXNG con la API JSON abierta. Se prueban en orden y
# se recuerda la que funcione, para no reintentar las caídas en cada búsqueda.
# El usuario puede apuntar a la suya con ANDROMEDA_SEARXNG_URL (`docker run
# -d -p 8888:8080 searxng/searxng`), que además mantiene sus búsquedas privadas.
_SEARXNG_PUBLIC = (
    "https://searx.be",
    "https://search.inetol.net",
    "https://priv.au",
    "https://searxng.site",
)
_searxng_working: str | None = None


def _searxng_instances() -> list[str]:
    """Instancias a probar: la del usuario primero, luego la que ya funcionó."""
    import os
    propia = (os.environ.get("ANDROMEDA_SEARXNG_URL") or "").strip().rstrip("/")
    orden = [propia] if propia else []
    if _searxng_working and _searxng_working not in orden:
        orden.append(_searxng_working)
    orden += [u for u in _SEARXNG_PUBLIC if u not in orden]
    return orden


# Si ninguna instancia pública responde, no se vuelve a intentar durante un
# rato. En los registros de Pau las públicas devolvían 403 en TODAS las
# búsquedas, y cada intento costaba entre 1 y 3 segundos antes de pasar a
# DuckDuckGo. Una instancia propia configurada no entra en esta pausa.
_searxng_pausa_hasta = 0.0
_ultimo_motor_ok: str | None = None
_PAUSA_SEARXNG_S = 900


async def _search_searxng(query: str, max_results: int, timeout: float) -> list[dict]:
    import os as _os
    import time as _time
    global _searxng_pausa_hasta
    propia = bool(_os.environ.get("ANDROMEDA_SEARXNG_URL"))
    if not propia and _time.monotonic() < _searxng_pausa_hasta:
        raise RuntimeError("SearXNG en pausa (las instancias públicas no responden)")
    try:
        resultados = await _search_searxng_intento(query, max_results, timeout)
    except Exception:
        if not propia:
            _searxng_pausa_hasta = _time.monotonic() + _PAUSA_SEARXNG_S
        raise
    return resultados


async def _search_searxng_intento(query: str, max_results: int, timeout: float) -> list[dict]:
    """Consulta una instancia de SearXNG a través de su API JSON."""
    global _searxng_working
    ultimo_error = "sin instancias"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for base in _searxng_instances():
            try:
                resp = await client.get(
                    f"{base}/search",
                    params={"q": query, "format": "json", "language": "auto"},
                    headers={"User-Agent": _UA, "Accept": "application/json"},
                    timeout=timeout,
                )
                if resp.status_code != 200:
                    # 403 suele significar que esa instancia tiene la API JSON
                    # desactivada (es lo habitual en las públicas, para evitar
                    # abuso). Se reintenta leyendo el HTML, que sí está abierto.
                    if resp.status_code in (403, 404):
                        html = await _searxng_html(client, base, query, timeout)
                        if html:
                            _searxng_working = base
                            return html[:max_results]
                    ultimo_error = f"HTTP {resp.status_code}"
                    continue
                try:
                    datos = resp.json().get("results", []) or []
                except ValueError:
                    # Respondió 200 pero con HTML: misma situación.
                    html = await _searxng_html(client, base, query, timeout)
                    if html:
                        _searxng_working = base
                        return html[:max_results]
                    ultimo_error = "respuesta no es JSON"
                    continue
                salida = [
                    {
                        "title": (r.get("title") or "").strip(),
                        "snippet": _strip_html(r.get("content") or "")[:300],
                        "url": r.get("url") or "",
                    }
                    for r in datos[:max_results]
                    if r.get("title") and r.get("url")
                ]
                if salida:
                    _searxng_working = base      # recordar la que responde
                    return salida
                ultimo_error = "sin resultados"
            except Exception as exc:             # noqa: BLE001
                ultimo_error = f"{type(exc).__name__}"
                continue
    raise RuntimeError(f"ninguna instancia SearXNG respondió ({ultimo_error})")



async def _searxng_html(client, base: str, query: str, timeout: float) -> list[dict]:
    """Lee los resultados de SearXNG desde su HTML.

    La mayoría de instancias públicas desactivan `format=json` para evitar
    abuso, pero la interfaz web sigue abierta. Sin este respaldo, SearXNG
    fallaba en casi todas las instancias públicas y la búsqueda caía siempre a
    los motores de raspado, que es justo lo que se quería evitar.
    """
    try:
        resp = await client.get(
            f"{base}/search",
            params={"q": query},
            headers={"User-Agent": _UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        html = resp.text
    except Exception:
        return []

    resultados = []
    # Estructura de SearXNG: <article class="result">…<a href="…"><h3>título</h3>
    for bloque in re.findall(r'<article[^>]*class="[^"]*result[^"]*"(.*?)</article>',
                             html, re.S | re.I)[:20]:
        m_url = re.search(r'<a[^>]+href="(https?://[^"]+)"', bloque)
        m_tit = re.search(r'<h3[^>]*>(.*?)</h3>', bloque, re.S)
        if not (m_url and m_tit):
            continue
        m_desc = re.search(r'<p[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</p>',
                           bloque, re.S | re.I)
        resultados.append({
            "title": _strip_html(m_tit.group(1)).strip(),
            "snippet": _strip_html(m_desc.group(1)).strip()[:300] if m_desc else "",
            "url": m_url.group(1),
        })
    return resultados

async def _search_ddg_html(query: str, max_results: int, timeout: float) -> list[dict]:
    """DuckDuckGo HTML. User-Agent de navegador real: con uno genérico devuelve 403."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(
            DDG_HTML,
            data={"q": query},
            headers={"User-Agent": _UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return _parse_ddg_html(resp.text, max_results)


async def _search_ddg_lite(query: str, max_results: int, timeout: float) -> list[dict]:
    """Versión "lite" de DuckDuckGo: HTML más simple y estable que la normal."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={"User-Agent": _UA},
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return _parse_ddg_lite(resp.text, max_results)


async def _search_wikipedia(query: str, max_results: int, timeout: float) -> list[dict]:
    """Último recurso: API de Wikipedia.

    No sirve para precios ni noticias, pero para preguntas enciclopédicas da una
    respuesta real en vez de nada, y su API es estable y no bloquea.
    """
    import os
    lang = (os.environ.get("ANDROMEDA_LANGUAGE", "en") or "en").strip().lower()[:2]
    if lang not in ("es", "en", "de", "fr"):
        lang = "en"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "srlimit": max_results, "format": "json"},
            headers={"User-Agent": "Andromeda/1.0 (local AI assistant)"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        out = []
        for item in (resp.json().get("query", {}).get("search", []) or [])[:max_results]:
            title = item.get("title", "")
            out.append({
                "title": title,
                "snippet": _strip_html(item.get("snippet", "")),
                "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
            })
        return out


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Extrae resultados del HTML de DuckDuckGo (sin dependencias externas).

    Se procesa cada resultado por separado. El patrón anterior era
    `título.*?(snippet)?`: como `.*?` es perezoso y el grupo opcional, el motor
    casaba `.*?` con nada y se saltaba el texto SIEMPRE. El modelo recibía solo
    títulos, sin contenido con el que responder.
    """
    import re
    results = []
    titulos = list(re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL))
    for i, m in enumerate(titulos):
        fin = titulos[i + 1].start() if i + 1 < len(titulos) else len(html)
        bloque = html[m.end():fin]
        ms = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div|td)>', bloque, re.DOTALL)
        url = m.group(1)
        title = _strip_html(m.group(2) or "")
        snippet = _strip_html(ms.group(1)) if ms else ""
        if title and url:
            results.append({"title": title, "snippet": snippet[:300], "url": url})
        if len(results) >= max_results:
            break
    return results


def _parse_ddg_lite(html: str, max_results: int) -> list[dict]:
    """Extrae resultados de lite.duckduckgo.com (tabla simple de enlaces)."""
    import re
    results = []
    pattern = re.compile(r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         re.DOTALL)
    snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
    for i, m in enumerate(pattern.finditer(html)):
        title = _strip_html(m.group(2) or "")
        if not title:
            continue
        results.append({
            "title": title,
            "snippet": _strip_html(snippets[i]) if i < len(snippets) else "",
            "url": m.group(1),
        })
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


# Pedir que se cree o cambie algo no es pedir información actual. Sin esta
# regla, "créame una página web" o "mejora la página web" buscaban en internet:
# segundos perdidos y el prompt lleno de anuncios de creadores de webs.
_TAREA = re.compile(
    # En cualquier punto de la frase: "Aquí está la imagen, ahora crea la página
    # web" empezaba por otra cosa y buscaba en internet.
    r"(^|[,.;:!?]\s*|\s(y|and|ahora|now|luego|then)\s+)"
    r"(a ver,?\s+|oye,?\s+|por favor,?\s+|please,?\s+|ahora\s+|now\s+)?"
    r"(quiero que me |necesito que me |puedes |podrías |can you |could you |please )?"
    r"(crea|créame|creame|crear|crees|hazme|haz|genera|generar|escribe|escríbeme|redacta|"
    r"añade|agrega|mejora|mejorar|modifica|edita|corrige|cambia|arregla|diseña|programa|"
    r"implementa|refactoriza|traduce|resume|create|make|build|write|add|improve|edit|fix|"
    r"change|design|code|implement|refactor|translate|summarize|erstelle|schreibe|"
    r"verbessere|ändere|crée|écris|améliore|modifie|corrige|创建|写|改进|修改)\b",
    re.IGNORECASE)
_PIDE_BUSCAR = re.compile(
    r"\b(busca|buscar|búscame|investiga|search|look up|google|find out|suche|such|"
    r"recherche|cherche)\b|搜索|查一下", re.IGNORECASE)


def needs_web_search(prompt: str) -> bool:
    """
    Heurística: ¿este prompt se beneficiaría de buscar en internet?

    Detecta preguntas sobre actualidad, datos que cambian, eventos, deportes,
    personas, lugares y cualquier hecho que un modelo local no puede saber con
    fiabilidad (y que tiende a alucinar). Mejor pecar de buscar de más en
    preguntas factuales que dejar al modelo inventar.
    """
    if prompt and _TAREA.search(prompt) and not _PIDE_BUSCAR.search(prompt):
        return False
    import unicodedata as _ud
    p = "".join(c for c in _ud.normalize("NFD", prompt.lower())
                if _ud.category(c) != "Mn")

    # Triggers explícitos de actualidad / petición de búsqueda
    triggers = [
        "ultimo", "ultima", "reciente", "actual", "ahora", "hoy", "ayer",
        "2023", "2024", "2025", "2026", "este ano", "este mes",
        "noticia", "precio", "cotizacion", "cuanto cuesta", "cuanto vale",
        "latest", "current", "news", "price", "today", "recent",
        "busca", "search", "internet", "google", "en linea",
        # Eventos y resultados (lo que falló con el mundial)
        "mundial", "champions", "liga", "partido", "resultado", "marcador",
        "gano", "ganador", "campeon", "clasificacion", "posicion",
        "elecciones", "presidente", "ministro", "premio", "oscar",
        # Preguntas sobre entidades cambiantes
        "quien es", "quien gano", "quien es el", "como ha quedado",
        "como quedo", "que paso con", "que paso en", "estado de",
        "version de", "cuando sale", "cuando es", "fecha de",
        # Equivalentes en inglés. La heurística estaba muy sesgada al español y
        # fallaba en preguntas obvias: "when is X launching", "who won X",
        # "is X out yet" no disparaban búsqueda y el modelo respondía de memoria.
        "when is", "when does", "when will", "when did", "release date",
        "launching", "launch date", "comes out", "coming out", "out yet",
        "who won", "who is the", "who are the", "how much is", "how much does",
        "cost", "available", "version of", "update", "new version",
        "world cup", "championship", "election", "score", "results",
        # "web" suelta disparaba búsquedas en "créame una página web": solo
        # cuenta cuando se pide buscar EN la web.
        "en la web", "en internet", "on the web", "in the web", "search the web",
        "im web", "im internet", "sur le web", "sur internet", "网上",
        # ── Alemán ───────────────────────────────────────────────────────
        "wann", "wann kommt", "wann erscheint", "erscheinungsdatum",
        "neueste", "neuste", "aktuell", "aktuelle", "heute", "gestern",
        "preis", "kostet", "wie viel", "nachrichten", "suche", "such",
        "wer hat gewonnen", "wer ist", "ergebnis", "wahl", "version von",
        # ── Chino ────────────────────────────────────────────────────────
        "什么时候", "何时", "发布日期", "上市", "最新", "现在", "今天", "昨天",
        "价格", "多少钱", "新闻", "搜索", "查一下", "谁赢", "谁是", "结果",
        "版本", "更新", "世界杯", "选举",
        # ── Francés ──────────────────────────────────────────────────────
        "quand", "quand sort", "date de sortie", "dernier", "derniere",
        "dernière", "actuel", "actuelle", "aujourd", "hier", "prix",
        "combien coute", "combien coûte", "actualite", "actualité",
        "cherche", "recherche", "qui a gagne", "qui a gagné", "qui est",
        "resultat", "résultat", "election", "élection", "version de",
        "coupe du monde", "mise a jour", "mise à jour",
        # Variantes que aparecían en el uso real y no estaban cubiertas
        "se lanza", "lanzamiento", "sale a la venta", "disponible",
        "erzahl mir uber", "erzähl mir über", "介绍一下", "parle-moi de",
        "parle moi de", "was kostet",
    ]
    if any(t in p for t in triggers):
        return True

    # Preguntas factuales sobre personas/lugares/organizaciones concretas:
    # patrón "¿quién/qué/cuándo/dónde ... [Nombre Propio]?" suele necesitar datos
    # frescos. Si hay un nombre propio (palabra capitalizada que no es la primera)
    # junto a una palabra interrogativa, buscamos.
    import re as _re
    has_question = any(w in p for w in ("quien", "que ", "cuando", "donde", "cuanto", "cual"))
    # Se quitan los signos de apertura (¿¡) y las comillas iniciales: con ellos
    # la primera palabra dejaba de estar "al principio" y "¿Cuál es la
    # diferencia entre TCP y UDP?" contaba "Cuál" como nombre propio, así que
    # CUALQUIER pregunta en español que empezara por ¿ buscaba en internet.
    _texto = _re.sub(r"^[\s¿¡\"'«(\[]+", "", prompt or "")
    _interrogativos = {"cuál", "cual", "qué", "que", "quién", "quien", "cómo", "como",
                       "cuándo", "cuando", "dónde", "donde", "cuánto", "cuanto", "por"}
    proper_nouns = [w for w in _re.findall(
        r"(?<!^)(?<![.!?¿¡]\s)(?<![¿¡])\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}", _texto)
        if w.lower() not in _interrogativos]
    if has_question and len(proper_nouns) >= 1:
        return True

    # Entidades cuyo estado CAMBIA con el tiempo. Preguntar "háblame de
    # minecraft" no contiene ninguna palabra de actualidad, pero la respuesta
    # útil sí depende de datos actuales (versión, novedades, contenido). Sin
    # buscar, el modelo rellena con su entrenamiento y lo presenta como cierto:
    # en una prueba real inventó biomas y criaturas de una versión que no
    # existe, con total seguridad.
    #
    # No se trata de buscar siempre, sino de reconocer las categorías donde
    # "lo que el modelo recuerda" y "lo que es cierto hoy" divergen.
    cambiantes = (
        # software y videojuegos
        "minecraft", "fortnite", "windows", "macos", "android", "ios", "linux",
        "chrome", "firefox", "python", "javascript", "react", "node",
        "juego", "game", "app", "aplicacion", "software", "programa",
        # empresas y productos
        "iphone", "samsung", "tesla", "openai", "google", "microsoft", "apple",
        "nvidia", "amd", "intel", "playstation", "xbox", "nintendo",
        # temas intrínsecamente actuales
        "modelo", "model", "gpu", "cpu", "criptomoneda", "bitcoin",
        "gta", "chatgpt", "claude", "gemini", "llama", "copilot",
        "steam", "epic games", "discord", "spotify", "netflix", "youtube",
        "twitter", "instagram", "tiktok", "whatsapp", "telegram",
        "mundial", "world cup", "champions", "olimpiadas", "olympics",
    )
    menciona_entidad = any(e in p for e in cambiantes)
    # Verbos de "cuéntame sobre X": el usuario espera información, no opinión.
    pide_informacion = any(v in p for v in (
        # español
        "sobre", "habla", "cuenta", "dime", "explica", "que es", "informacion",
        # inglés
        "about", "tell me", "what is", "info", "describe",
        # alemán
        "uber", "über", "erzahl", "erzähl", "was ist", "sag mir",
        # chino
        "关于", "介绍", "告诉我", "是什么",
        # francés
        "sur", "parle", "dis-moi", "dis moi", "qu'est-ce", "quest-ce",
        "presente", "présente",
    ))
    if menciona_entidad and pide_informacion:
        return True

    return False


# ── Lectura directa de URLs ────────────────────────────────────────────────

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# Páginas de resultados de buscadores: leerlas da el HTML del buscador, no la
# información. Es mejor tratar su término de búsqueda como una consulta normal.
_SEARCH_PAGE = re.compile(
    r"^https?://(www\.)?(google|bing|duckduckgo|yahoo|ecosia|startpage)\.[a-z.]+/",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    """URLs presentes en el texto del usuario."""
    return _URL_RE.findall(text or "")


def search_terms_from_url(url: str) -> str:
    """Si la URL es una búsqueda de Google/Bing/etc., devuelve lo que se buscaba."""
    if not _SEARCH_PAGE.match(url or ""):
        return ""
    from urllib.parse import parse_qs, unquote, urlparse
    qs = parse_qs(urlparse(url).query)
    for key in ("q", "query", "p", "text"):
        if key in qs and qs[key]:
            return unquote(qs[key][0]).strip()
    return ""


async def fetch_url(url: str, timeout: float = 12.0, max_chars: int = 6000) -> dict | None:
    """Descarga una página y devuelve su texto legible.

    Cuando el usuario pega un enlace espera que se lea, no que el modelo
    adivine su contenido o intente una herramienta que quizá no tenga.

    Returns:
        {"url", "title", "text"} o None si no se pudo leer.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": _UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.info(f"fetch_url: {url} devolvió HTTP {resp.status_code}")
                return None
            html = resp.text
    except Exception as exc:                              # noqa: BLE001
        logger.info(f"fetch_url: {url} falló ({type(exc).__name__})")
        return None

    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        title = _strip_html(m.group(1))[:200]

    # Fuera todo lo que no es contenido antes de limpiar etiquetas.
    body = re.sub(r"<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", " ",
                  html, flags=re.S | re.I)
    text = _strip_html(body)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return {"url": url, "title": title, "text": text[:max_chars]}
