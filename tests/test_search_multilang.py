"""Batería multilingüe de detección de búsqueda web.

Cientos de casos generados combinando plantillas × entidades × 5 idiomas. La
heurística estaba muy sesgada al español y fallaba en inglés con preguntas
obvias ("when is X launching", "who won X"): el modelo respondía de memoria e
inventaba datos actuales.

Dos errores igual de malos, y por eso se prueban ambos lados:
  • NO buscar cuando hace falta → el modelo inventa y lo presenta como cierto
  • buscar cuando no hace falta → gasta segundos y contexto sin aportar nada
"""
import logging

import pytest

logging.disable(logging.CRITICAL)

# Plantillas por idioma: preguntas cuya respuesta correcta CAMBIA con el tiempo
_PLANTILLAS = {
    "es": ["cuándo sale {e}", "cuándo se lanza {e}", "qué precio tiene {e}",
           "cuánto cuesta {e}", "últimas noticias de {e}", "busca info de {e}",
           "cuál es la última versión de {e}", "háblame de {e}", "qué es {e}",
           "cuéntame sobre {e}"],
    "en": ["when is {e} launching", "when does {e} release", "how much is {e}",
           "what is the price of {e}", "latest news about {e}", "search for {e}",
           "latest version of {e}", "tell me about {e}", "what is {e}",
           "is {e} out yet", "{e} release date"],
    "de": ["wann kommt {e}", "wann erscheint {e}", "wie viel kostet {e}",
           "preis von {e}", "neueste nachrichten über {e}", "suche nach {e}",
           "neueste version von {e}", "erzähl mir über {e}", "was ist {e}",
           "erscheinungsdatum von {e}"],
    "zh": ["{e}什么时候发布", "{e}的价格是多少", "{e}最新消息", "搜索{e}",
           "{e}最新版本", "介绍一下{e}", "{e}是什么", "{e}发布日期",
           "告诉我关于{e}的信息"],
    "fr": ["quand sort {e}", "quand est la sortie de {e}", "combien coûte {e}",
           "prix de {e}", "dernières actualités sur {e}", "cherche {e}",
           "dernière version de {e}", "parle-moi de {e}", "qu'est-ce que {e}",
           "date de sortie de {e}"],
}

_ENTIDADES = ["gta 6", "minecraft", "windows 11", "el iphone", "python", "react",
              "bitcoin", "tesla", "chatgpt", "playstation 5", "nvidia"]

# Preguntas atemporales: buscar aquí solo añade espera
_ATEMPORALES = {
    "es": ["explícame la recursividad", "escríbeme un poema sobre el mar",
           "cuánto es 2+2", "hola qué tal", "traduce hola al inglés",
           "corrige esta frase", "qué es un puntero en C", "resume este texto"],
    "en": ["explain pointers in C", "write me a poem about the sea", "what is 2+2",
           "hello how are you", "translate hello to spanish", "fix this sentence",
           "what is recursion", "summarize this text"],
    "de": ["erkläre mir rekursion", "schreib ein gedicht", "was ist 2+2",
           "hallo wie geht es dir"],
    "zh": ["解释一下递归", "写一首诗", "2加2等于几", "你好吗"],
    "fr": ["explique-moi la récursivité", "écris un poème", "combien font 2+2",
           "bonjour ça va"],
}


def _casos_positivos():
    return [(p.format(e=e), lang)
            for lang, plantillas in _PLANTILLAS.items()
            for p in plantillas for e in _ENTIDADES]


def _casos_negativos():
    return [(f, lang) for lang, frases in _ATEMPORALES.items() for f in frases]


@pytest.mark.parametrize("texto,lang", _casos_positivos())
def test_current_questions_trigger_search(texto, lang):
    from app.core.web_search import needs_web_search
    assert needs_web_search(texto), f"[{lang}] no buscaría: {texto!r}"


@pytest.mark.parametrize("texto,lang", _casos_negativos())
def test_timeless_questions_do_not_search(texto, lang):
    from app.core.web_search import needs_web_search
    assert not needs_web_search(texto), f"[{lang}] buscaría de más: {texto!r}"


def test_coverage_is_broad_enough():
    """Deja constancia del tamaño de la batería: si alguien recorta las
    plantillas, este test lo delata."""
    assert len(_casos_positivos()) >= 500
    assert len(_casos_negativos()) >= 25
    assert set(_PLANTILLAS) == {"es", "en", "de", "zh", "fr"}


