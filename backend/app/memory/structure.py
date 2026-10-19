"""
structure.py — Memoria organizada como la de Claude.

El perfil guarda datos sueltos por tema ("gustos:azul", "nombre", "nota:x"). Aquí
se agrupan en secciones y "archivos" legibles, cada uno con resumen y fecha:

    Tú        → Preferencias, Perfil
    Temas     → Gustos, Favoritos, Objetivos, Tecnología, Rutina
    Áreas     → Proyectos
    Personas  → una ficha por persona mencionada
    Notas     → lo que el usuario pidió recordar explícitamente

También: clasificación de temas sensibles (salud, religión, política,
orientación) para el interruptor "Incluir temas sensibles", y búsqueda en
conversaciones anteriores para "Buscar y consultar conversaciones".
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# tema → (sección, archivo)
_MAPA = {
    "idioma": ("tu", "preferencias"), "estilo": ("tu", "preferencias"),
    "preferencia": ("tu", "preferencias"),
    "nombre": ("tu", "perfil"), "edad": ("tu", "perfil"), "ubicacion": ("tu", "perfil"),
    "profesion": ("tu", "perfil"), "empresa": ("tu", "perfil"), "estudios": ("tu", "perfil"),
    "nivel": ("tu", "perfil"),
    "gustos": ("temas", "gustos"), "disgustos": ("temas", "gustos"),
    "favoritos": ("temas", "favoritos"), "objetivo": ("temas", "objetivos"),
    "stack": ("temas", "tecnologia"), "hardware": ("temas", "tecnologia"),
    "horario": ("temas", "rutina"),
    "proyecto": ("areas", "proyectos"),
    "persona": ("personas", None), "nota": ("notas", "notas"),
    "perfil": ("tu", "perfil"),
}

# Tema base con el que se guardan los datos de un archivo reescrito entero.
BASE_DE_ARCHIVO = {"preferencias": "preferencia", "perfil": "perfil", "gustos": "gustos",
                   "favoritos": "favoritos", "objetivos": "objetivo", "tecnologia": "stack",
                   "rutina": "horario", "proyectos": "proyecto", "notas": "nota"}
SECCIONES = ["tu", "temas", "areas", "personas", "notas"]

# Temas sensibles (salud, religión, política, orientación sexual, datos muy
# personales). Con el interruptor apagado no se guardan y se eliminan.
_SENSIBLE = re.compile(
    r"\b(peso|adelgazar|dieta|enferm\w*|m[eé]dic\w*|medicaci[oó]n|pastillas?|diagn[oó]stic\w*|"
    r"ansiedad|depresi[oó]n|terapia|psic[oó]log\w*|embaraz\w*|diabetes|c[aá]ncer|alergi\w*|"
    r"relig\w*|dios|cat[oó]lic\w*|musulm[aá]n\w*|jud[ií]\w*|ateo|"
    r"pol[ií]tic\w*|vot\w+|partido|izquierda|derecha|"
    r"gay|lesbiana|bisexual|trans|orientaci[oó]n sexual|"
    r"weight|diet|illness|disease|medication|anxiety|depression|therapy|pregnan\w*|"
    r"religio\w*|politic\w*|sexual orientation)\b",
    re.IGNORECASE)


def es_sensible(texto: str) -> bool:
    return bool(_SENSIBLE.search(texto or ""))


def _base(topic: str) -> str:
    return topic.split(":", 1)[0]


def seccion_de(topic: str) -> tuple[str, str]:
    base = _base(topic)
    seccion, archivo = _MAPA.get(base, ("notas", "notas"))
    if seccion == "personas":
        partes = topic.split(":")
        archivo = "persona:" + (partes[1] if len(partes) > 1 and partes[1] else "sin-nombre")
    return seccion, archivo


def _ts(valor) -> float:
    """Fecha como número. El perfil guarda la general en ISO ('2026-09-26T08:01:14Z')
    y las de cada dato como número: convertirla sin más daba error 500."""
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str) and valor:
        from datetime import datetime
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def build(profile) -> dict:
    """Memoria agrupada en secciones → archivos → datos, con fecha por archivo."""
    datos = profile.get() if profile is not None else {}
    facts = datos.get("facts", {}) or {}
    meta = datos.get("meta", {}) or {}
    secciones = {s: {} for s in SECCIONES}
    for key, texto in facts.items():
        sec, arch = seccion_de(key)
        f = secciones[sec].setdefault(arch, {"id": arch, "facts": [], "updated": 0.0})
        f["facts"].append({"key": key, "text": texto, "sensitive": es_sensible(texto)})
        f["updated"] = max(f["updated"], _ts(meta.get(key) or datos.get("updated_at")))
    salida = []
    for s in SECCIONES:
        archivos = sorted(secciones[s].values(), key=lambda a: -a["updated"])
        for a in archivos:
            a["summary"] = "; ".join(x["text"] for x in a["facts"])[:220]
            if a["id"].startswith("persona:"):
                a["name"] = a["id"].split(":", 1)[1].replace("-", " ").title()
        salida.append({"id": s, "files": archivos})
    return {"sections": salida, "manual": datos.get("manual", "")}


# ── Conversaciones anteriores ─────────────────────────────────────────────

_REMITE_PASADO = re.compile(
    r"\b(la otra vez|el otro d[ií]a|antes (hablamos|me dijiste|te dije)|te (dije|cont[eé]|pregunt[eé])|"
    r"me (dijiste|recomendaste|explicaste)|recuerdas|te acuerdas|hablamos de|en otra conversaci[oó]n|"
    r"last time|we (talked|discussed)|you (told|said|recommended)|i (told|asked) you|do you remember|"
    r"letztes mal|tu (m'as dit|te souviens)|上次|你还记得)\b",
    re.IGNORECASE)
_VACIAS = {"que", "los", "las", "una", "uno", "del", "por", "para", "con", "como", "este", "the",
           "and", "you", "dije", "dijo", "eso", "esto", "sea", "hay", "fue",
           "esta", "the", "and", "for", "you", "that", "what", "dijiste", "dije", "otra",
           "vez", "recuerdas", "acuerdas", "hablamos", "sobre", "about"}


def _palabras(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]{3,}", (t or "").lower()) if w not in _VACIAS}


def remite_a_conversaciones(prompt: str) -> bool:
    return bool(_REMITE_PASADO.search(prompt or ""))


def search_past_chats(ui_state_path: Path, prompt: str, *, excluir: list[str] | None = None,
                      k: int = 2, max_chars: int = 600) -> list[dict]:
    """Fragmentos de conversaciones anteriores relevantes para el mensaje.

    Busca por palabras en común entre el mensaje y cada intercambio (pregunta +
    respuesta), descartando la conversación actual.
    """
    try:
        convs = json.loads(ui_state_path.read_text(encoding="utf-8")).get("andromeda_conversations") or []
    except (OSError, ValueError, AttributeError):
        return []
    claves = _palabras(prompt)
    if not claves:
        return []
    excluir_set = {(e or "").strip()[:200] for e in (excluir or [])}
    candidatos = []
    for conv in convs:
        msgs = conv.get("messages") or []
        for i, m in enumerate(msgs):
            if m.get("role") != "user" or (m.get("content") or "").strip()[:200] in excluir_set:
                continue
            resp = next((x for x in msgs[i + 1:i + 2] if x.get("role") == "assistant"), None)
            texto = f"{m.get('content', '')} {resp.get('content', '') if resp else ''}"
            puntos = len(claves & _palabras(texto))
            # Con pocas palabras clave basta una coincidencia (la búsqueda solo se
            # activa cuando el usuario remite explícitamente a otra conversación).
            if puntos >= max(1, round(len(claves) * 0.4)):
                candidatos.append((puntos, {
                    "title": conv.get("title") or "",
                    "date": conv.get("createdAt") or "",
                    "user": (m.get("content") or "")[:250],
                    "assistant": (resp.get("content") if resp else "")[:max_chars],
                }))
    candidatos.sort(key=lambda c: -c[0])
    return [c for _, c in candidatos[:k]]


# ── Importar memoria de otro asistente ────────────────────────────────────

IMPORT_PROMPT = {
    "es": ("Escribe todo lo que recuerdas sobre mí de nuestras conversaciones: quién soy, "
           "a qué me dedico, mis preferencias sobre cómo responderme, mis proyectos, gustos, "
           "objetivos y personas importantes. Una línea por dato, empezando cada línea con "
           "«- ». Solo hechos, sin comentarios."),
    "en": ("Write everything you remember about me from our conversations: who I am, what I "
           "do, how I like you to respond, my projects, interests, goals and important people. "
           "One fact per line, each starting with \"- \". Facts only, no commentary."),
}


def parse_import(texto: str) -> list[str]:
    """Líneas de datos de un texto exportado por otro asistente."""
    lineas = []
    for l in (texto or "").splitlines():
        l = re.sub(r"^\s*([-*•·]|\d+[.)])\s*", "", l).strip()
        if 6 <= len(l) <= 400 and not l.endswith(":"):
            lineas.append(l)
    return lineas[:300]


def now() -> float:
    return time.time()



def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", (texto or "").lower()).strip("-")[:48]


def file_lines(profile, seccion: str, archivo: str) -> list[str]:
    facts = (profile.get() or {}).get("facts", {}) or {}
    return [t for k, t in facts.items() if seccion_de(k) == (seccion, archivo)]


def replace_file(profile, seccion: str, archivo: str, lineas: list[str]) -> int:
    """Sustituye el contenido de un "archivo" de memoria por estas líneas."""
    for clave in list((profile.get() or {}).get("facts", {})):
        if seccion_de(clave) == (seccion, archivo):
            profile.delete_fact(clave)
    base = ("persona:" + archivo.split(":", 1)[1]) if archivo.startswith("persona:") \
        else BASE_DE_ARCHIVO.get(archivo, "nota")
    n = 0
    for linea in lineas:
        linea = linea.strip()
        if linea:
            profile.upsert_fact(f"{base}:{_slug(linea)}", linea[:500])
            n += 1
    return n


def edit_prompt(nombre: str, lineas: list[str], instruccion: str) -> str:
    """Prompt para que la IA local aplique un cambio descrito en lenguaje natural."""
    actual = "\n".join(f"- {l}" for l in lineas) or "(vacío)"
    return ("Mantienes la memoria que un asistente guarda sobre su usuario. Este es el "
            f"tema «{nombre}» tal y como está ahora:\n\n{actual}\n\n"
            f"El usuario pide este cambio: {instruccion}\n\n"
            "Devuelve SOLO el tema completo ya actualizado: una línea por dato, cada una "
            "empezando por «- ». Conserva lo que no se pide cambiar. Sin comentarios ni "
            "explicaciones. Si el usuario pide borrarlo todo, devuelve una sola línea «- (vacío)».")


def parse_edit(texto: str) -> list[str]:
    import re as _re
    texto = _re.sub(r"<think>.*?</think>", "", texto or "", flags=_re.S)
    salida = []
    for l in texto.splitlines():
        m = _re.match(r"^\s*[-*•]\s+(.+)$", l)
        if m and m.group(1).strip().lower() not in ("(vacío)", "(empty)", "vacío"):
            salida.append(m.group(1).strip())
    return salida
