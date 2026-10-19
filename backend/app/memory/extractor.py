"""
Extracción automática de memorias a partir de los mensajes del usuario.

Estilo Claude: mientras conversas, se guardan automáticamente datos clave y
preferencias persistentes, además de cualquier cosa que el usuario pida
recordar explícitamente. Usa patrones (rápido, sin coste, fiable) en lugar de
pedírselo al LLM, que en modelos locales pequeños es lento y poco de fiar.

Cada memoria lleva un 'topic' (idioma, nombre, stack…). Cuando llega una nueva
memoria del mismo topic, REEMPLAZA a la anterior — así "ahora trabajo con Rust"
sustituye a "trabajo con FastAPI" en vez de acumular contradicciones.

Devuelve una lista de (contenido, categoría, topic). Vacía si no hay nada que
merezca recordarse — la mayoría de los turnos no generan memoria.
"""
from __future__ import annotations

import re

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


# Peticiones EXPLÍCITAS de recordar: "recuerda que...", "remember that...", etc.
# El contenido va DESPUÉS del verbo: "recuerda que <esto>".
_EXPLICIT = re.compile(
    r"\b(recuerda|recordar|guarda|guardar|apunta|anota|no olvides|save|store|"
    r"ten en cuenta|recuérdame|remember|note that|keep in mind|don't forget|"
    r"merke dir|notiere|retiens|souviens-toi)\b[:\s]+(que\s+|that\s+)?(?P<c>.+)",
    re.IGNORECASE | re.DOTALL,
)

# La petición puede ir al FINAL: "es viernes, recuérdalo" / "..., remember it please".
# Sin esto se capturaba como hecho lo que viene detrás del verbo ("it please"),
# guardando basura en memoria y contaminando las respuestas siguientes.
_EXPLICIT_TRAILING = re.compile(
    r"^(?P<c>.+?)[,;\.\s]+"
    r"(recuérdalo|recuerdalo|guárdalo|guardalo|apúntalo|apuntalo|anótalo|anotalo|"
    r"no lo olvides|tenlo en cuenta|"
    r"remember (it|this|that)|note (it|this)|keep (it|this) in mind|don't forget (it|this))"
    r"[\s,\.!]*(please|por favor|porfavor|bitte|s'il te plaît)?[\s\.!]*$",
    re.IGNORECASE | re.DOTALL,
)

# Cosas que nunca son un hecho útil aunque sigan al verbo de recordar.
_JUNK_CONTENT = re.compile(
    r"^(it|this|that|esto|eso|lo|please|por favor|porfavor|ok|vale)"
    r"[\s\.,!]*(please|por favor|porfavor)?[\s\.,!]*$",
    re.IGNORECASE,
)

# (patrón, topic). El topic agrupa memorias para poder ACTUALIZARLAS.
# Multilingüe (ES + EN + algo de DE/FR). Cada patrón captura group(0) como frase.
_PATTERNS = [
    # ── Idioma de respuesta ──────────────────────────────────────────────
    (re.compile(r"\b(prefiero|quiero|me gustaría)\b.{0,40}\b(hablar|hables|habla|responder|respondas|responde)\b.{0,30}\b(en|en el idioma)\b\s+\w+", re.IGNORECASE), "idioma"),
    (re.compile(r"\b(háblame|hablame|respóndeme|respondeme|escríbeme|escribeme)\b.{0,20}\b(en)\b\s+\w+", re.IGNORECASE), "idioma"),
    (re.compile(r"\b(reply|respond|answer|talk to me|write to me)\b.{0,25}\b(in)\b\s+(english|spanish|german|french|chinese|catalan|\w+)", re.IGNORECASE), "idioma"),
    # ── Nombre / identidad ───────────────────────────────────────────────
    (re.compile(r"\b(me llamo|mi nombre es|puedes llamarme|llámame)\b\s+[\wÁ-ú]+", re.IGNORECASE), "nombre"),
    (re.compile(r"\b(my name is|i am called|call me|i'm)\b\s+[A-Z][\w]+", re.IGNORECASE), "nombre"),
    (re.compile(r"\b(ich heiße|mein name ist|je m'appelle|je suis)\b\s+[A-ZÀ-Ü]\w+", re.IGNORECASE), "nombre"),
    # ── Ubicación ────────────────────────────────────────────────────────
    (re.compile(r"\b(vivo en|resido en|soy de|estoy basado en|me ubico en)\b\s+[A-ZÁ-ú][\wÁ-ú\s]{1,30}", re.IGNORECASE), "ubicacion"),
    (re.compile(r"\b(i live in|i'm from|i am from|i'm based in|i reside in|i'm located in)\b\s+[\w\s]{2,30}", re.IGNORECASE), "ubicacion"),
    (re.compile(r"\b(ich wohne in|ich komme aus|j'habite à|je viens de)\b\s+[\wÀ-Ü]{2,30}", re.IGNORECASE), "ubicacion"),
    # ── Profesión / rol ──────────────────────────────────────────────────
    (re.compile(r"\b(trabajo como|me dedico a|mi profesión es|mi puesto es|mi rol es)\b\s+.{2,40}", re.IGNORECASE), "profesion"),
    (re.compile(r"\bsoy\s+(un |una )?(desarrollador\w*|programador\w*|ingenier\w+|estudiante|diseñador\w*|analista|profesor\w*|médic\w+|abogad\w+|consultor\w*|científic\w+|arquitect\w+|gestor\w*|fundador\w*|emprendedor\w*)", re.IGNORECASE), "profesion"),
    (re.compile(r"\b(i work as|my job is|my role is|i'm a|i am a|i'm an|i am an)\b\s+(an? )?(developer|engineer|student|designer|analyst|teacher|doctor|lawyer|consultant|scientist|architect|manager|founder|researcher|programmer)\w*", re.IGNORECASE), "profesion"),
    # ── Empresa / estudios ───────────────────────────────────────────────
    (re.compile(r"\b(trabajo en|trabajo para|mi empresa es)\b\s+.{2,40}", re.IGNORECASE), "empresa"),
    (re.compile(r"\b(i work at|i work for|my company is|my employer is)\b\s+.{2,40}", re.IGNORECASE), "empresa"),
    (re.compile(r"\b(estudio|estoy estudiando|curso|estoy cursando)\b\s+.{2,40}", re.IGNORECASE), "estudios"),
    (re.compile(r"\b(i'm studying|i am studying|i study|i'm learning|i am learning|i study at)\b\s+.{2,40}", re.IGNORECASE), "estudios"),
    # ── Proyecto ─────────────────────────────────────────────────────────
    (re.compile(r"\b(estoy (construyendo|desarrollando|haciendo|trabajando en)|mi proyecto (es|se llama|trata))\b\s+.{2,50}", re.IGNORECASE), "proyecto"),
    (re.compile(r"\b(i'm building|i am building|i'm working on|i am working on|my project is|i'm developing|i'm making)\b\s+.{2,50}", re.IGNORECASE), "proyecto"),
    # ── Objetivo / meta ──────────────────────────────────────────────────
    (re.compile(r"\b(mi objetivo es|mi meta es|quiero (ser|llegar a|convertirme en|conseguir)|aspiro a)\b\s+.{2,60}", re.IGNORECASE), "objetivo"),
    (re.compile(r"\b(my goal is|my aim is|i want to (be|become|get|reach)|i aim to|my dream is|i'm aiming for)\b\s+.{2,60}", re.IGNORECASE), "objetivo"),
    # ── Trabajo / stack técnico ──────────────────────────────────────────
    (re.compile(r"\b(trabajo con|uso|utilizo|programo en|mi stack es|desarrollo en|mi lenguaje es)\b\s+[\w\.\+#]+(\s*(y|,)\s*[\w\.\+#]+)*", re.IGNORECASE), "stack"),
    (re.compile(r"\b(i work with|i use|i code in|i develop in|my stack is|i program in|my main language is)\b\s+[\w\.\+#]+(\s*(and|,)\s*[\w\.\+#]+)*", re.IGNORECASE), "stack"),
    # ── Hardware / equipo ────────────────────────────────────────────────
    (re.compile(r"\b(mi (gpu|tarjeta|cpu|equipo|pc|portátil|máquina|ordenador) es|tengo (una|un)\s+(rtx|gtx|radeon|ryzen|intel|nvidia|m1|m2|m3|m4))\b.{0,40}", re.IGNORECASE), "hardware"),
    (re.compile(r"\b(my (gpu|cpu|machine|rig|laptop|pc|setup) is|i have (a|an)\s+(rtx|gtx|radeon|ryzen|intel|nvidia|m1|m2|m3|m4))\b.{0,40}", re.IGNORECASE), "hardware"),
    # ── Edad ─────────────────────────────────────────────────────────────
    (re.compile(r"\btengo\s+\d{1,2}\s+años\b", re.IGNORECASE), "edad"),
    (re.compile(r"\bi('?m| am)\s+\d{1,2}\s+years old\b", re.IGNORECASE), "edad"),
    # ── Nivel / experiencia ──────────────────────────────────────────────
    (re.compile(r"\b(soy (principiante|novato|junior|senior|experto|avanzado)|tengo\s+\d+\s+años de experiencia)\b.{0,30}", re.IGNORECASE), "nivel"),
    (re.compile(r"\b(i'm a (beginner|junior|senior|expert)|i'm (new to|experienced)|i have\s+\d+\s+years of experience)\b.{0,30}", re.IGNORECASE), "nivel"),
    # ── Personas ("mi hermano se llama Marc") ────────────────────────────
    (re.compile(r"\bmi\s+(hermano|hermana|novio|novia|pareja|mujer|marido|esposa|esposo|madre|"
                r"padre|hijo|hija|jefe|jefa|amigo|amiga|compañero|compañera|profesor|profesora|"
                r"perro|perra|gato|gata)\s+se\s+llama\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+", re.IGNORECASE), "persona"),
    (re.compile(r"\bmy\s+(brother|sister|boyfriend|girlfriend|partner|wife|husband|mother|mum|mom|"
                r"father|dad|son|daughter|boss|friend|colleague|teacher|dog|cat)(['’]s name is|\s+is called|"
                r"\s+is named)\s+[A-Z][\w]+", re.IGNORECASE), "persona"),
    # ── Favoritos ("mi color favorito es el azul") ───────────────────────
    (re.compile(r"\b(mi|mis)\s+\w+(\s+\w+)?\s+favorit[oa]s?\s+(es|son)\b.{1,40}", re.IGNORECASE), "favoritos"),
    (re.compile(r"\bmy\s+favou?rite\s+\w+(\s+\w+)?\s+(is|are)\b.{1,40}", re.IGNORECASE), "favoritos"),
    (re.compile(r"\b(mein|meine)\s+lieblings\w+\s+(ist|sind)\b.{1,40}", re.IGNORECASE), "favoritos"),
    (re.compile(r"\b(mon|ma|mes)\s+\w+\s+préférée?s?\s+(est|sont)\b.{1,40}", re.IGNORECASE), "favoritos"),
    (re.compile(r"我最喜欢的.{1,30}"), "favoritos"),
    # ── Objetivos personales ("quiero bajar de peso") ────────────────────
    (re.compile(r"\b(me gustaría|quiero|quisiera|necesito|tengo que|intento|estoy intentando|mi plan es)\s+"
                r"(bajar|perder|ganar|aprender|mejorar|dejar de|empezar a|conseguir|ahorrar|correr|leer|viajar|"
                r"cambiar|terminar|aprobar|encontrar|montar|lanzar|mudarme)\b.{1,50}", re.IGNORECASE), "objetivo"),
    (re.compile(r"\b(i want to|i'd like to|i would like to|i need to|i'm trying to|i am trying to|my plan is to)\s+"
                r"(lose|gain|learn|improve|quit|stop|start|save|run|read|travel|change|finish|pass|find|build|launch|move)\b.{1,50}",
                re.IGNORECASE), "objetivo"),
    (re.compile(r"\b(ich möchte|ich will)\s+.{2,40}\s+(abnehmen|lernen|sparen|verbessern|aufhören)\b", re.IGNORECASE), "objetivo"),
    (re.compile(r"\b(je veux|j'aimerais|je voudrais)\s+(perdre|maigrir|apprendre|améliorer|arrêter|commencer|économiser)\b.{1,50}", re.IGNORECASE), "objetivo"),
    (re.compile(r"我想(要)?(减肥|学习|提高|戒|开始|存钱).{0,30}"), "objetivo"),
    # ── Gustos ───────────────────────────────────────────────────────────
    (re.compile(r"\b(me gusta|me encanta|me apasiona|disfruto|soy fan de)\b\s+.{2,50}", re.IGNORECASE), "gustos"),
    (re.compile(r"\b(i like|i love|i enjoy|i'm passionate about|i'm a fan of)\b\s+.{2,50}", re.IGNORECASE), "gustos"),
    (re.compile(r"\b(ich mag|ich liebe)\b\s+.{2,50}", re.IGNORECASE), "gustos"),
    (re.compile(r"(j'aime|j'adore)\s+.{2,50}", re.IGNORECASE), "gustos"),
    (re.compile(r"我(喜欢|爱).{1,30}"), "gustos"),
    # ── Disgustos ────────────────────────────────────────────────────────
    (re.compile(r"\b(no me gusta|odio|detesto|no soporto|me molesta)\b\s+.{2,50}", re.IGNORECASE), "disgustos"),
    (re.compile(r"\b(i don'?t like|i hate|i dislike|i can'?t stand)\b\s+.{2,50}", re.IGNORECASE), "disgustos"),
    # ── Horario / disponibilidad ─────────────────────────────────────────
    (re.compile(r"\b(trabajo los|estoy disponible los|mi horario es|suelo trabajar)\b\s+.{2,40}", re.IGNORECASE), "horario"),
    (re.compile(r"\b(i work on|i'm available on|my schedule is|i'm free on|i usually work)\b\s+.{2,40}", re.IGNORECASE), "horario"),
    # ── Estilo de respuesta ──────────────────────────────────────────────
    (re.compile(r"\b(sé (breve|conciso|directo)|respuestas (cortas|breves|detalladas)|explica paso a paso|no te enrolles|ve al grano)\b", re.IGNORECASE), "estilo"),
    (re.compile(r"\b(be (brief|concise|direct|detailed)|keep it short|short answers|step by step|don'?t ramble|get to the point)\b", re.IGNORECASE), "estilo"),
    # ── Preferencia general (catch-all, ES + EN) ─────────────────────────
    (re.compile(r"\b(prefiero|mi preferencia es)\b\s+.{3,60}", re.IGNORECASE), "preferencia"),
    (re.compile(r"\b(i prefer|i'd rather|i like to)\b\s+.{3,60}", re.IGNORECASE), "preferencia"),
]

# Señales de que el usuario CAMBIA algo previo ("ya no…", "now…", "actually…").
_UPDATE_HINT = re.compile(r"\b(ya no|ahora|he cambiado|cambié|cambie|en realidad|"
                          r"actualiza|corrige|mejor|no longer|now|actually|"
                          r"i've changed|changed to|update|correction)\b", re.IGNORECASE)

# Preguntas/comandos efímeros que NO se guardan (ES + EN).
_SKIP = re.compile(r"^\s*(qué|que|cómo|como|cuándo|cuando|dónde|donde|por qué|porque|"
                   r"puedes|crea|haz|dame|escribe|genera|muéstrame|explica|"
                   r"what|how|when|where|why|who|can you|could you|create|make|"
                   r"give me|write|generate|show me|explain|tell me|please)\b", re.IGNORECASE)


# Coletillas que el usuario añade pero que NO deben guardarse como contenido.
_TAIL_NOISE = re.compile(
    r"[,;\.]?\s*(guárdalo|guardalo|guarda esto|recuérdalo|recuerdalo|"
    r"si puedes|por favor|porfa|en (la )?memoria|en tu memoria)\b.*$",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Quita coletillas tipo 'guárdalo en la memoria si puedes' y puntuación final."""
    t = _TAIL_NOISE.sub("", text).strip()
    return t.rstrip(" .,;")



_PRONOMBRES = {"this", "that", "it", "these", "those", "esto", "eso", "esta", "este",
               "aquello", "lo", "la", "el", "please", "por", "favor", "ok", "vale"}


def _tiene_contenido(texto: str) -> bool:
    """Al menos dos palabras con significado (no pronombres ni números sueltos).

    "this. 42" pasaba el filtro anterior y se guardaba como dato del usuario.
    """
    palabras = [w for w in re.findall(r"[A-Za-zÀ-ÿ\u4e00-\u9fff]{3,}", texto.lower())
                if w not in _PRONOMBRES]
    return len(palabras) >= 2 or any("\u4e00" <= c <= "\u9fff" for c in texto)


# Temas que ACUMULAN valores en vez de reemplazarse. Antes todo tema se
# reemplazaba: decir "me gusta el fútbol" (o "me gusta cómo ha quedado") borraba
# el "me gusta el azul" anterior. Nombre, idioma o ubicación sí son únicos.
MULTI_TOPICS = {"gustos", "disgustos", "favoritos", "objetivo", "proyecto", "stack"}


def topic_key(topic: str, contenido: str) -> str:
    """Clave de almacenamiento: única por tema, o por tema + contenido."""
    if topic == "persona":
        nombre = re.findall(r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+$", contenido.strip())
        return f"persona:{(nombre[0] if nombre else 'sin-nombre').lower()}"
    if topic.startswith("explicit:"):
        base = "nota"
    elif topic in MULTI_TOPICS:
        base = topic
    else:
        return topic
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", contenido.lower()).strip("-")[:48]
    return f"{base}:{slug}"

def extract_memories(user_message: str) -> list[tuple[str, str, str]]:
    """Devuelve [(contenido, categoría, topic)] a guardar desde un mensaje."""
    if not user_message or len(user_message.strip()) < 4:
        return []
    msg = user_message.strip()
    found: list[tuple[str, str, str]] = []

    # 1) Petición explícita de recordar → máxima prioridad, pero seguimos para
    #    detectar si además encaja en un topic específico (idioma/nombre/stack)
    #    y así guardar con ESE topic en vez de "explicit" genérico.
    explicit_content = None
    # Primero la forma con la petición al final ("X, recuérdalo"), porque en esa
    # construcción el hecho está ANTES del verbo.
    mt = _EXPLICIT_TRAILING.match(msg.strip())
    if mt:
        explicit_content = _clean(mt.group("c").strip())
    else:
        m = _EXPLICIT.search(msg)
        if m:
            explicit_content = _clean(m.group("c").strip())
    # "save in andromeda's memory X" → X. Sin esto se guardaba literalmente
    # "In andromeda's memory the iphone…" (visto en un registro real).
    if explicit_content:
        explicit_content = re.sub(
            r"^(in|en|to|a)\s+(the\s+|la\s+)?(andromeda['’]?s?\s+)?(memory|memoria)(\s+de\s+andromeda)?[\s:,]*",
            "", explicit_content, flags=re.IGNORECASE).strip()
    # Descartar capturas sin contenido real ("it please", "esto", "this. 42").
    if explicit_content and (_JUNK_CONTENT.match(explicit_content)
                             or len(explicit_content) < 6
                             or not _tiene_contenido(explicit_content)):
        diag.log("memory", "captura descartada por vacía",
                 data={"capturado": explicit_content[:60]}, level="warn")
        explicit_content = None

    # 2) No extraer de preguntas/comandos (salvo que sea petición explícita).
    if not explicit_content and _SKIP.match(msg):
        return found

    # 3) Preferencias persistentes por patrón. Los específicos (idioma, nombre,
    #    stack) tienen prioridad: si uno casa, NO añadimos el genérico
    #    "preferencia" para la misma frase (evita duplicados como idioma+preferencia).
    matched_specific = False
    # Topics donde una cláusula tras 'y'/'and'/coma es ruido (no una lista).
    _TRIM = {"ubicacion", "empresa", "profesion", "objetivo", "nivel", "horario", "estudios", "proyecto"}
    for pat, topic in _PATTERNS:
        if topic == "preferencia" and matched_specific:
            continue  # ya cubierto por un patrón más específico
        mm = pat.search(msg)
        if mm:
            frag = _clean(mm.group(0).strip())
            if topic in _TRIM:
                frag = re.split(r"\s+(?:y|and|und|et)\s+|,\s*", frag, maxsplit=1)[0].strip()
            if 3 <= len(frag) <= 120:
                found.append((frag, "preference", topic))
                if topic != "preferencia":
                    matched_specific = True

    # 4) Si hubo petición explícita pero NINGÚN patrón la cubrió, guardarla.
    if explicit_content and not found:
        topic = "explicit:" + " ".join(explicit_content.lower().split()[:3])
        found.append((explicit_content, "explicit", topic))

    # Deduplicar por topic conservando orden
    seen = set()
    uniq = []
    for c, cat, tp in found:
        if tp not in seen:
            seen.add(tp)
            uniq.append((c, cat, tp))
    # "me gusta el negro? lo odio" / "no me gusta X": no es un gusto. Se
    # descartan los gustos de un mensaje que expresa rechazo.
    if re.search(r"\b(lo odio|la odio|odio|detesto|no me gusta|i hate|hate it|don't like|"
                 r"do not like|ich hasse|je déteste)\b|讨厌|不喜欢", user_message or "", re.IGNORECASE):
        uniq = [u for u in uniq if u[2] not in ("gustos", "favoritos")]
    return uniq[:5]

