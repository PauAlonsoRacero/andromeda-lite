"""
linear_orchestrator.py — Orquestador lineal de Andromeda Lite.

A diferencia de la orquestación multi-IA de Pro (varios especialistas en paralelo
+ fusión), Lite usa UN solo modelo y ajusta su POTENCIA de forma lineal según la
complejidad de cada petición:

    prompt simple   → nivel bajo  (modelo pequeño, rápido, menos VRAM)
    prompt complejo → nivel alto  (modelo grande, más capaz)

La complejidad se estima con señales del propio prompt (longitud, tipo de tarea,
palabras que indican razonamiento, código o análisis profundo) y se acota por el
hardware disponible: nunca se elige un nivel que el equipo no pueda mover.

El usuario puede forzar un nivel manualmente (low/mid/high/ultra) o dejar 'auto',
en cuyo caso decide este orquestador. Es determinista y explicable: devuelve la
razón de la decisión para mostrarla en la UI.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ["low", "mid", "high", "ultra"]

# Señales léxicas que empujan la complejidad hacia arriba.
_HEAVY_HINTS = (
    "demuestra", "demostrar", "analiza a fondo", "análisis detallado", "optimiza",
    "refactoriza", "arquitectura", "diseña un sistema", "explica en detalle",
    "compara exhaustivamente", "razona paso a paso", "prueba matemática",
    "algoritmo", "complejidad computacional", "concurrencia", "multihilo",
    "prove", "derive", "step by step", "in depth", "comprehensive", "design a system",
    "debuggea", "debuggear", "depura", "stack trace", "segmentation fault", "traceback",
)
_CODE_HINTS = (
    "```", "def ", "class ", "function", "import ", "SELECT ", "async ",
    "regex", "compile",
)
_LIGHT_HINTS = (
    "hola", "gracias", "resume en una línea", "sí o no", "traduce", "qué hora",
    "define brevemente", "lista rápida", "hello", "thanks", "tldr",
)


@dataclass
class PowerDecision:
    level: str            # low | mid | high | ultra
    score: float          # 0..1 complejidad estimada
    reason: str           # explicación legible
    forced: bool          # True si lo fijó el usuario


def _complexity_score(prompt: str) -> float:
    """Estima la complejidad del prompt en [0, 1] a partir de señales objetivas.

    Filosofía: la NATURALEZA de la tarea manda sobre la longitud. Pedir
    "refactoriza esta función" es trabajo de alto nivel aunque sea corto, así que
    una sola señal pesada ya empuja a 'high'; dos o más (o señal pesada + código)
    tienden a 'ultra'. La longitud y el nº de preguntas solo afinan al alza.
    """
    if not prompt:
        return 0.0
    p = prompt.lower()
    score = 0.0

    heavy = sum(1 for h in _HEAVY_HINTS if h in p)
    code = sum(1 for h in _CODE_HINTS if h.lower() in p)
    explica = any(v in p for v in ("explica", "explain", "cómo funciona", "how does",
                                   "por qué", "why", "describe", "diferencia entre",
                                   "resume", "summarize", "compara", "compare"))
    # Verbos de redacción/creación → tarea de nivel medio aunque sea corta
    crea = any(v in p for v in ("escribe", "redacta", "genera", "crea ", "write ",
                                "draft", "compose", "haz un", "hazme un", "dame un"))

    # 1. Señales de tarea pesada — la primera vale mucho (lleva a 'high'),
    #    las siguientes suman menos (rendimientos decrecientes hacia 'ultra').
    if heavy >= 1:
        score += 0.55                       # una sola señal pesada → ya 'high'
        score += min(heavy - 1, 2) * 0.10   # cada señal extra acerca a 'ultra'

    # 2. Señales de código (un bloque, def, traceback…) → trabajo técnico real
    if code >= 1:
        score += 0.34
        score += min(code - 1, 2) * 0.06

    # 3. Verbos explicativos/comparativos → complejidad media de base
    if explica:
        score += 0.30

    # 4. Verbos de redacción/creación → nivel medio de base
    if crea:
        score += 0.26

    # 5. Longitud: afina al alza, no domina (~500+ chars = petición sustancial)
    score += min(len(prompt) / 500.0, 1.0) * 0.20

    # 6. Varias preguntas/pasos en una misma petición
    questions = p.count("?") + p.count("¿")
    score += min(questions / 5.0, 1.0) * 0.10

    # 7. Señales de tarea trivial (saludos, traducir, una línea) → bajan fuerte,
    #    pero solo si no hay ninguna señal de tarea compleja.
    light = sum(1 for h in _LIGHT_HINTS if h in p)
    if light and heavy == 0 and code == 0 and len(prompt) < 120:
        score -= 0.45

    return max(0.0, min(score, 1.0))


def _score_to_level(score: float) -> str:
    """Mapea la complejidad a un nivel de potencia (lineal por tramos)."""
    if score < 0.22:
        return "low"
    if score < 0.50:
        return "mid"
    if score < 0.66:
        return "high"
    return "ultra"


def _cap_by_hardware(level: str, max_level: str | None) -> str:
    """No permite subir por encima de lo que el hardware puede mover."""
    if not max_level or max_level not in LEVELS:
        return level
    return level if LEVELS.index(level) <= LEVELS.index(max_level) else max_level


def decide_power(
    prompt: str,
    *,
    user_choice: str | None = None,
    hardware_max_level: str | None = None,
    available_levels: set[str] | None = None,
) -> PowerDecision:
    """Decide el nivel de potencia para esta petición.

    - user_choice: 'auto' o un nivel concreto. Si es un nivel, manda (forzado).
    - hardware_max_level: tope que el equipo puede ejecutar.
    - available_levels: niveles que tienen un modelo asignado de verdad.
    """
    choice = (user_choice or "auto").strip().lower()

    # Nivel forzado por el usuario
    if choice in LEVELS:
        lvl = _cap_by_hardware(choice, hardware_max_level)
        if available_levels and lvl not in available_levels:
            lvl = _nearest_available(lvl, available_levels)
        return PowerDecision(level=lvl, score=-1.0, forced=True,
                             reason=f"Nivel fijado manualmente: {lvl}.")

    # Auto: estimar complejidad y mapear a nivel
    score = _complexity_score(prompt)
    lvl = _score_to_level(score)
    capped = _cap_by_hardware(lvl, hardware_max_level)
    if available_levels and capped not in available_levels:
        capped = _nearest_available(capped, available_levels)

    if score < 0.22:
        why = "petición breve y directa → potencia baja (rápido y eficiente)"
    elif score < 0.50:
        why = "petición de complejidad media → potencia media"
    elif score < 0.66:
        why = "tarea elaborada (razonamiento/código) → potencia alta"
    else:
        why = "tarea muy compleja → potencia máxima"
    if capped != lvl:
        why = (f"se estimó '{lvl}' pero se ajustó a '{capped}' "
               f"por el hardware o los modelos disponibles")

    return PowerDecision(level=capped, score=round(score, 2), forced=False, reason=why)


def _nearest_available(level: str, available: set[str]) -> str:
    """Devuelve el nivel disponible más cercano hacia abajo; si no, hacia arriba."""
    idx = LEVELS.index(level)
    for i in range(idx, -1, -1):
        if LEVELS[i] in available:
            return LEVELS[i]
    for i in range(idx + 1, len(LEVELS)):
        if LEVELS[i] in available:
            return LEVELS[i]
    return level


def fallback_chain(level: str, available_levels: set[str] | None = None) -> list[str]:
    """Cadena de niveles a probar si el actual no arranca por carga.

    Devuelve [nivel_actual, inferior_1, inferior_2, ...] hacia abajo. Si se pasan
    los niveles con modelo disponible, filtra a esos. Sirve para que el executor
    reintente con un modelo más ligero cuando el hardware/software no soporta la
    carga (out of memory, timeout, error del runtime), en vez de fallar.
    """
    if level not in LEVELS:
        level = "mid"
    idx = LEVELS.index(level)
    chain = [LEVELS[i] for i in range(idx, -1, -1)]   # actual y todos los inferiores
    if available_levels:
        chain = [l for l in chain if l in available_levels]
        if not chain:  # nada disponible hacia abajo: usa lo más cercano que haya
            chain = [_nearest_available(level, available_levels)]
    return chain


# ── Frases placeholder mientras se genera la respuesta ──────────────────────
# La UI las muestra durante la espera para que la experiencia sea fluida, en vez
# de anunciar cambios de nivel o gastar tokens del modelo en mensajes de estado.
# No se piden al modelo: son locales e instantáneas.
_PLACEHOLDERS = {
    "low":   ["Un momento…", "Enseguida…", "Voy…"],
    "mid":   ["Pensando…", "Procesando tu petición…", "Dame un segundo…"],
    "high":  ["Analizando con calma…", "Trabajando en ello…", "Razonando la respuesta…"],
    "ultra": ["Esto requiere pensar a fondo…", "Procesando una tarea compleja…",
              "Dame un momento, vale la pena hacerlo bien…"],
}
_PLACEHOLDER_FALLBACK = "Ajustando para tu equipo…"


def loading_phrase(level: str, *, downgraded: bool = False, prompt: str = "") -> str:
    """Frase de espera. Si el prompt sugiere una acción concreta (crear archivo,
    página web, etc.) devuelve una frase descriptiva tipo Claude; si no, una
    frase acorde al nivel de potencia."""
    import random
    if downgraded:
        return _PLACEHOLDER_FALLBACK
    # Frases contextuales según lo que pide el usuario
    p = (prompt or "").lower()
    if any(k in p for k in ("página web", "pagina web", "html", "web", "landing", "sitio")):
        return random.choice(["Construyendo la página web…", "Escribiendo el HTML…",
                              "Diseñando la página…"])
    if any(k in p for k in ("word", ".docx", "documento")):
        return random.choice(["Redactando el documento…", "Creando el Word…"])
    if any(k in p for k in ("excel", ".xlsx", "hoja de cálculo", "tabla")):
        return random.choice(["Montando la hoja de cálculo…", "Creando la tabla…"])
    if any(k in p for k in (".pdf",)):
        return "Generando el PDF…"
    if any(k in p for k in ("modifica", "edita", "mejora", "cambia", "actualiza", "corrige")):
        return random.choice(["Leyendo el archivo…", "Aplicando los cambios…",
                              "Editando el contenido…"])
    if any(k in p for k in ("borra", "elimina", "mueve", "renombra")):
        return "Organizando los archivos…"
    if any(k in p for k in ("crea", "genera", "escribe", "guarda", "archivo", "fichero")):
        return random.choice(["Creando el archivo…", "Escribiendo el contenido…",
                              "Preparando el archivo…"])
    if any(k in p for k in ("código", "codigo", "script", "función", "funcion", "programa")):
        return random.choice(["Escribiendo el código…", "Programando la solución…"])
    options = _PLACEHOLDERS.get(level, _PLACEHOLDERS["mid"])
    return random.choice(options)
