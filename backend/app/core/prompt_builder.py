"""
prompt_builder.py — Construcción del prompt que recibe el modelo.

Antes esto vivía duplicado en dos sitios: `routes/chat.py` (camino streaming) y
`core/router.py` (camino no-streaming). Cada mejora había que implementarla dos
veces y, con la edición Pro, cuatro. En la práctica se desincronizaron: la
compactación de contexto y el perfil de memoria solo existían en `router.py`, de
modo que en el modo streaming —el que se usa— no se aplicaban nunca.

Peor aún: los bloques se escribían uno detrás de otro sobre la misma variable,
sin un orden explícito. Varios se SOBRESCRIBÍAN entre sí, y la fecha del sistema
acababa sepultada al final de miles de caracteres, donde los modelos pequeños la
ignoran (respondían con la fecha de su entrenamiento).

Aquí el orden es explícito y está justificado:

    1. AVISOS       — restricciones que el modelo debe respetar por encima de todo
    2. SKILL        — instrucciones de comportamiento para este tipo de tarea
    3. MEMORIA      — lo que sabemos del usuario
    4. DOCUMENTOS   — contexto recuperado de sus ficheros (RAG)
    5. WEB          — resultados de búsqueda o página leída
    6. HISTORIAL    — conversación previa, ya compactada
    7. MENSAJE      — lo que ha escrito ahora

Lo que condiciona *cómo* responder va antes; los datos van después; el mensaje
del usuario siempre al final, que es la posición a la que más atención prestan
los modelos.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("andromeda.prompt")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


@dataclass
class PromptParts:
    """Piezas del prompt final, cada una opcional.

    Se acumulan en lugar de sobrescribirse: antes, dos bloques que escribían
    sobre la misma variable se pisaban silenciosamente.
    """
    notice: str = ""            # avisos y restricciones
    skill: str = ""             # instrucciones de la skill activa
    memory: str = ""            # perfil y recuerdos del usuario
    documents: str = ""         # fragmentos del RAG
    web: str = ""               # resultados de búsqueda o página leída
    history: str = ""           # conversación previa
    message: str = ""           # el mensaje del usuario

    # Metadatos para la interfaz (qué se usó al responder)
    meta: dict = field(default_factory=dict)

    def render(self) -> str:
        """Ensambla el prompt final en el orden establecido."""
        bloques = [
            self.notice,
            self.skill,
            self.memory,
            self.documents,
            self.web,
            self.history,
        ]
        cuerpo = "\n\n".join(b.strip() for b in bloques if b and b.strip())
        final = self.message if not cuerpo else f"{cuerpo}\n\n---\n\n{self.message}"
        # El prompt final es LA pieza clave para diagnosticar: casi todos los
        # fallos de comportamiento se explican mirando qué recibió el modelo.
        diag.log("prompt", "prompt final construido",
                 data={
                     "total_chars": len(final),
                     "avisos": len(self.notice), "skill": len(self.skill),
                     "memoria": len(self.memory), "documentos": len(self.documents),
                     "web": len(self.web), "historial": len(self.history),
                 },
                 detail=final, level="success")
        return final


def expand_slash(prompt: str) -> str:
    """Expande un comando de barra a su instrucción completa."""
    try:
        from app.core.slash_commands import expand
        return expand(prompt)
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Slash commands no disponibles: {exc}")
        return prompt


def add_skill(parts: PromptParts, prompt: str, skill_registry) -> None:
    """Activa la skill que encaje con el mensaje, si hay alguna."""
    if skill_registry is None:
        diag.log("skills", "sin registro de skills", level="warn")
        return
    try:
        hits = skill_registry.match(prompt or "", k=1)
        if hits:
            parts.skill = f"[Skill activa: {hits[0].name}]\n{hits[0].body}"
            parts.meta["skill_used"] = hits[0].name
            diag.log("skills", f"activada: {hits[0].name}",
                     data={"chars": len(parts.skill)}, level="success")
        else:
            diag.log("skills", "ninguna skill encaja con el mensaje")
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Skills no disponibles: {exc}")
        diag.log("skills", "fallo al buscar skill", detail=str(exc), level="error")


def add_memory(parts: PromptParts, prompt: str, memory_profile, memory_store,
               incognito: bool) -> None:
    """Añade el perfil del usuario y los recuerdos relevantes.

    En incógnito no se consulta nada: el usuario ha pedido explícitamente que
    esa conversación no se relacione con lo que sabemos de él.
    """
    if incognito:
        return
    trozos = []
    if memory_profile is not None:
        try:
            bloque = memory_profile.render()
            if bloque:
                trozos.append(bloque)
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Perfil de memoria no disponible: {exc}")
    if memory_store is not None:
        try:
            import asyncio
            hits = memory_store.search(prompt or "", k=3)
            if asyncio.iscoroutine(hits):
                hits = None                               # el llamador async usa add_memory_async
            if hits:
                lineas = "\n".join(f"- {h['content']}" for h in hits)
                trozos.append(f"RECUERDOS RELEVANTES:\n{lineas}")
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Memoria semántica no disponible: {exc}")
    if trozos:
        parts.memory = "\n\n".join(trozos)


async def add_memory_async(parts: PromptParts, prompt: str, memory_profile,
                           memory_store, incognito: bool) -> None:
    """Versión asíncrona: la búsqueda semántica necesita await."""
    if incognito:
        diag.log("memory", "omitida (modo incógnito)")
        return
    trozos = []
    if memory_profile is not None:
        try:
            bloque = memory_profile.render()
            if bloque:
                trozos.append(bloque)
                diag.log("memory", "perfil incluido",
                         data={"chars": len(bloque)}, detail=bloque[:400])
            else:
                diag.log("memory", "perfil vacío")
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Perfil de memoria no disponible: {exc}")
            diag.log("memory", "fallo al leer el perfil", detail=str(exc), level="error")
    if memory_store is not None and es_consulta_generica(prompt):
        diag.log("memory", "pregunta genérica: sin búsqueda de recuerdos")
    elif memory_store is not None:
        try:
            hits = await memory_store.search(prompt or "", k=3)
            # Cada dato se guarda en el perfil Y en el almacén semántico: sin este
            # filtro aparecía dos veces en el prompt (visto en registros reales).
            ya = " ".join(trozos).lower()
            norm = lambda t: re.sub(r"[^\w]+", " ", (t or "").lower()).strip()
            hits = [h for h in hits if norm(h.get("content")) not in norm(ya)]
            if hits:
                lineas = "\n".join(f"- {h['content']}" for h in hits)
                trozos.append(f"RECUERDOS RELEVANTES:\n{lineas}")
                parts.meta["memories_used"] = len(hits)
                diag.log("memory", f"{len(hits)} recuerdos recuperados",
                         detail=lineas, level="success")
            else:
                diag.log("memory", "sin recuerdos relevantes para este mensaje")
        except Exception as exc:                          # noqa: BLE001
            logger.debug(f"Memoria semántica no disponible: {exc}")
            diag.log("memory", "fallo en la búsqueda semántica",
                     detail=str(exc), level="error")
    if trozos:
        # Encabezado explícito: antes los datos entraban pegados al mensaje, sin
        # indicación, y un modelo pequeño respondía a "¿qué puedes hacer?"
        # hablando del color favorito del usuario.
        parts.memory = (
            "LO QUE SABES DEL USUARIO (contexto de fondo; úsalo SOLO si es relevante "
            "para su pregunta, sin mencionarlo si no viene al caso):\n"
            + "\n\n".join(trozos))


def add_documents(parts: PromptParts, prompt: str, rag_index, incognito: bool) -> None:
    """Recupera fragmentos relevantes de los documentos indexados."""
    if rag_index is None or incognito:
        diag.log("rag", "omitido",
                 data={"motivo": "incógnito" if incognito else "sin índice"})
        return
    try:
        hits = rag_index.query(prompt or "", k=3)
        diag.log("rag", f"{len(hits)} fragmentos recuperados",
                 data={"documentos": sorted({h['doc_id'] for h in hits})} if hits else {},
                 level="success" if hits else "info")
        if hits:
            ctx = "\n\n".join(f"[{h['doc_id']}] {h['text']}" for h in hits)
            parts.documents = (
                "Contexto relevante de los documentos del usuario "
                f"(cítalo por [id]):\n{ctx}"
            )
            parts.meta["rag_sources"] = sorted({h["doc_id"] for h in hits})
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"RAG no disponible: {exc}")


def add_web_results(parts: PromptParts, results: list[dict]) -> None:
    """Añade resultados de búsqueda web."""
    if not results:
        return
    listado = "\n".join(
        f"[{i + 1}] {r['title']}: {r['snippet']} ({r['url']})"
        for i, r in enumerate(results)
    )
    parts.web = (
        "Tienes acceso a estos resultados de búsqueda web actuales:\n\n"
        f"{listado}\n\n"
        "Úsalos para responder. Cita cada dato con su número [n] y, cuando el usuario "
        "busque algo concreto (un producto, un anuncio, una página), incluye el ENLACE "
        "completo en formato Markdown [título](url). Nunca digas que no puedes dar "
        "enlaces: los tienes aquí. No inventes URLs que no aparezcan en esta lista."
    )
    parts.meta["web_used"] = True


def add_web_page(parts: PromptParts, page: dict) -> None:
    """Añade el contenido de una página que el usuario ha compartido."""
    if not page:
        return
    parts.web = (
        f"Contenido de la página que ha compartido el usuario ({page['url']}):\n\n"
        f"{page.get('title', '')}\n{page.get('text', '')}\n\n"
        "Responde basándote en este contenido. Si no contiene lo que se "
        "pregunta, dilo claramente."
    )
    parts.meta["web_used"] = True


def add_notice(parts: PromptParts, texto: str) -> None:
    """Añade un aviso. Se acumulan en vez de sobrescribirse.

    Antes cada aviso pisaba al anterior, así que si coincidían dos (por ejemplo
    'sin resultados' y 'red desactivada') solo llegaba uno al modelo.
    """
    if not texto:
        return
    parts.notice = f"{parts.notice}\n{texto}".strip() if parts.notice else texto


async def add_history(parts: PromptParts, history: list[dict], context_window: int,
                      ollama_url: str = "", model: str = "") -> None:
    """Añade la conversación previa, compactándola si no cabe.

    La compactación solo existía en el camino no-streaming, así que en el modo
    normal las conversaciones largas se truncaban sin más y se perdía lo
    hablado al principio.
    """
    if not history:
        return
    # Defensa: si el último turno del historial es el propio mensaje actual,
    # se quita. Si no, el modelo lo recibe dos veces (visto en un registro real).
    ultimo = history[-1] if history else None
    if (ultimo and ultimo.get("role") == "user"
            and (ultimo.get("content") or "").strip()
            and (ultimo.get("content") or "").strip() in (parts.message or "")):
        history = history[:-1]
        if not history:
            return
    try:
        from app.core.compaction import compact_history
        presupuesto = max(400, context_window * 220)
        history, info = await compact_history(history, presupuesto,
                                              ollama_url=ollama_url, model=model)
        if info.get("compacted"):
            parts.meta["context_compacted"] = True
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Compactación no disponible: {exc}")
        history = history[-context_window:]

    lineas = "\n".join(
        f"{'Usuario' if m.get('role') == 'user' else 'Asistente'}: "
        f"{_resumir_turno(m.get('content') or '')[:600]}"
        for m in history[-context_window:]
    )
    parts.history = f"HISTORIAL:\n{lineas}"


# Palabras que sugieren que el usuario habla de sus archivos. Sin este filtro
# se inyectaría el listado del workspace en cada mensaje, gastando contexto.
_WORKSPACE_HINTS = (
    "archivo", "fichero", "documento", "html", "página", "pagina", "txt",
    "modifica", "edita", "mejora", "cambia", "actualiza", "añade", "agrega",
    "borra", "elimina", "crea", "guarda", ".docx", ".xlsx", ".pdf",
    "carpeta", "web",
)


_EDITAR = re.compile(r"\b(mejora|mejorar|modifica|modificar|edita|editar|cambia|cambiar|arregla|"
                     r"corrige|añade|agrega|actualiza|quita|improve|edit|fix|change|update|add to|"
                     r"verbessere|ändere|améliore|modifie|改进|修改)\b", re.IGNORECASE)
_CREAR = re.compile(r"\b(crea|créame|crear|crees|genera|nuevo|nueva|desde cero|create|new|"
                    r"from scratch|erstelle|neue|crée|nouveau|nouvelle|创建|新)\b", re.IGNORECASE)


def add_workspace(parts: PromptParts, prompt: str, incognito: bool,
                  has_images: bool = False) -> None:
    """Añade qué archivos existen en el workspace y el contenido reciente.

    Permite que la IA MODIFIQUE archivos ya creados en vez de duplicarlos:
    "mejora el index.html" necesita ver el index.html actual.
    """
    if incognito:
        return
    texto = (prompt or "").lower()
    if not any(k in texto for k in _WORKSPACE_HINTS):
        return
    try:
        from app.core.workspace import Workspace
        # ¿Contenido de los archivos o solo la lista? Antes se metía siempre el
        # contenido de los recientes: al pedir "crea index.html basado en la
        # web de la foto", el modelo copió pagina_web.html (que estaba en el
        # prompt) e ignoró la imagen. Contenido solo si se nombra un archivo o
        # se pide modificar algo existente; con imágenes o al crear, la lista.
        ws = Workspace()
        nombres = [f.path.lower() for f in ws.list()] if hasattr(ws, "list") else []
        nombra = any(n and n in texto for n in nombres)
        quiere_editar = bool(_EDITAR.search(texto)) and not _CREAR.search(texto)
        con_contenido = (nombra or quiere_editar) and not has_images
        bloque = ws.context_block(inline_text_files=3 if con_contenido else 0)
        if has_images and bloque:
            bloque += ("\n\nIMPORTANTE: la referencia para esta petición es la IMAGEN adjunta, "
                       "no los archivos anteriores.")
        if bloque:
            parts.documents = (f"{bloque}\n\n{parts.documents}".strip()
                               if parts.documents else bloque)
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Contexto del workspace no disponible: {exc}")


async def add_web_context(parts: PromptParts, *, prompt: str, settings,
                          incognito: bool, web_search: bool = True,
                          history: list | None = None, model: str = "") -> bool:
    """Búsqueda web y lectura de URLs, compartida por los dos caminos del chat.

    Antes vivía solo en el camino streaming. Pero la app de escritorio usa el
    camino SIN streaming (WKWebView no entrega el cuerpo de forma incremental),
    así que en escritorio no había búsqueda web en absoluto: el modelo solo
    tenía la herramienta MCP de fetch, y cuando fallaba repetía al usuario sus
    mensajes internos. Todas las mejoras de búsqueda se hacían en un camino que
    la aplicación principal no ejecutaba nunca.

    Devuelve True si se añadió contenido web al prompt.
    """
    import logging as _logging
    logger = _logging.getLogger("andromeda.web")
    web_used = False
    from app.core.flags import get_flag as _gf
    from app.observability import diagnostics as _dg
    _net_ok = _gf(settings, "andromeda_network_egress")
    _dg.log("chat", "nuevo mensaje",
            data={
                "incognito": incognito,
                "red_activa": _net_ok,
                "web_search_pedido": web_search,
                "historial_recibido": len(history or []),
                "modelo": model or "auto",
            },
            detail=prompt, level="success")
    if _net_ok and not incognito and web_search:
        from app.core.web_search import (
            clean_query, extract_urls, fetch_url, needs_web_search,
            search_terms_from_url, search_web,
        )

        # Si el usuario pega un enlace, espera que se lea. Antes esto
        # dependía de que el modelo supiera usar la herramienta MCP de
        # fetch, y cuando no la tenía respondía que "no pudo acceder".
        _urls = extract_urls(prompt)
        _search_query = _consulta_con_contexto(prompt, history)
        if _urls:
            _url = _urls[0]
            # Un enlace a resultados de Google no se lee: se busca lo
            # que el usuario buscaba en él.
            _terms = search_terms_from_url(_url)
            if _terms:
                _search_query = _terms
            else:
                _page = await fetch_url(_url)
                if _page:
                    web_used = True
                    add_web_page(parts, _page)
                    logger.info(f"Página leída: {_url}")
                else:
                    # Muchos sitios bloquean peticiones automáticas. En
                    # ese caso se busca por el nombre del dominio y el
                    # texto del usuario, en vez de dejar que el modelo
                    # improvise: sin aviso acababa repitiendo mensajes
                    # internos de las herramientas al usuario.
                    from urllib.parse import urlparse
                    _dominio = urlparse(_url).netloc.replace("www.", "")
                    _search_query = f"{_dominio} {clean_query(prompt)}"
                    add_notice(parts, (
                        f"AVISO: no se ha podido leer {_url} (el sitio bloquea el "
                        "acceso automático o no está disponible). Si la búsqueda "
                        "posterior no aporta datos, dile al usuario que no has "
                        "podido acceder a esa página. NO expliques detalles "
                        "técnicos de herramientas internas ni inventes el "
                        "contenido."
                    ))
                    logger.info(f"No se pudo leer {_url}; se buscará por dominio")

        from app.observability import diagnostics as _diag
        _quiere = needs_web_search(prompt)
        _diag.log("chat", f"¿buscar en internet? {'SÍ' if _quiere else 'NO'}",
                  data={"prompt": prompt[:120],
                        "urls_detectadas": len(_urls),
                        "consulta": _search_query[:80]},
                  level="info" if _quiere else "warn")
        if not web_used and _quiere:
            results = await search_web(_search_query, max_results=4)
            if results:
                web_used = True
                add_web_results(parts, results)
                logger.info(f"Web search: {len(results)} resultados inyectados")
            else:
                # Ningún motor devolvió nada. Distinguir "sin internet"
                # de "la búsqueda no encontró resultados" evita que el
                # modelo dé al usuario una explicación equivocada.
                from app.core.web_search import check_internet
                if await check_internet(timeout=2.0):
                    _aviso = ("se ha intentado buscar en internet pero la búsqueda "
                              "no ha devuelto resultados")
                    logger.info("Web search: sin resultados de ningún motor")
                else:
                    _aviso = "no hay conexión a internet ahora mismo"
                    logger.info("Web search: sin conexión a internet")
                add_notice(parts, (
                    f"AVISO: {_aviso}. NO inventes datos actuales (precios, fechas, "
                    "noticias): dile claramente al usuario que no has podido "
                    "consultar internet y responde solo con lo que sepas, "
                    "advirtiendo de que puede estar desactualizado."
                ))
    elif not incognito and web_search:
        # La búsqueda está apagada en Ajustes. Sin este aviso el modelo
        # responde "no tengo acceso a internet" sin más, y el usuario no
        # descubre nunca que existe un interruptor que puede encender.
        from app.core.web_search import needs_web_search as _nws
        if _nws(prompt):
            add_notice(parts, (
                "AVISO: el usuario pregunta algo que requeriría buscar en internet, "
                "pero la salida de red está DESACTIVADA en Ajustes de Andromeda. "
                "Explícale brevemente que puede activarla en "
                "Ajustes → Capacidades → 'Permitir salida de red' para que puedas "
                "buscar. Responde con lo que sepas, avisando de que tu información "
                "puede estar desactualizada."
            ))
            logger.info("Web search solicitada pero network_egress está desactivado")
    return web_used


# ── Órdenes sobre la memoria ──────────────────────────────────────────────
# "Borra la memoria" / "olvida que me gusta el azul" se ejecutan de forma
# determinista, sin depender del modelo. En un registro real, el modelo intentó
# borrar usando el conector MCP "memory" (un grafo de conocimiento distinto, que
# no es lo que el usuario ve en Andromeda), falló tres veces por argumentos
# mal formados y aun así dijo que lo había hecho.
_BORRAR_TODO = re.compile(
    r"\b(borra|borrar|elimina|eliminar|limpia|limpiar|vacía|vacia|vaciar|resetea|olvida|"
    r"clear|delete|erase|wipe|reset|forget|lösche|löschen|vergiss|efface|effacer|oublie|"
    r"réinitialise)\b.{0,40}\b(memoria|memory|gedächtnis|erinnerung|speicher|mémoire|"
    r"todo lo que sabes|everything you know|todo sobre mí|everything about me)\b"
    r"|\b(olvida|olvídalo|forget|vergiss|oublie)\s+(todo|everything|alles|tout)\b"
    r"|清除.{0,6}记忆|删除.{0,6}记忆|忘记所有",
    re.IGNORECASE)
# Olvidar algo CONCRETO. Se comprueba antes que "borrar todo": en un registro
# real, "podrías eliminar de memoria que me gusta el color negro?" borró TODA la
# memoria (3 datos y 8 recuerdos) porque solo se probaba el patrón general.
_OLVIDAR = re.compile(
    r"\b(olvida|olvídate de|forget|vergiss|oublie)\s+(que|lo de|that|about|dass)?\s*(?P<x>.{3,160})"
    r"|\b(borra|borrar|elimina|eliminar|quita|quitar|remove|delete|erase|lösche|efface|supprime)\b"
    r".{0,25}?\b(de|from|aus|de la|de ta)\s+(la\s+|tu\s+|mi\s+|the\s+|your\s+|my\s+|deinem\s+)?"
    r"(memoria|memory|gedächtnis|mémoire)\b[\s,:]*(que|that|dass|lo de|the fact that)?\s*(?P<y>.{3,160})",
    re.IGNORECASE)


def is_memory_command(prompt: str) -> bool:
    """¿El mensaje es una orden sobre la memoria? Entonces no se extraen datos
    de él: se guardaba "me gusta el color negro" al pedir justo olvidarlo."""
    t = (prompt or "").strip()
    return bool(_OLVIDAR.search(t) or _BORRAR_TODO.search(t))


async def handle_memory_commands(parts: PromptParts, prompt: str, memory_profile,
                                 memory_store, incognito: bool) -> str | None:
    """Ejecuta órdenes explícitas sobre la memoria. Devuelve qué se hizo."""
    if incognito or not prompt:
        return None
    texto = prompt.strip()

    m = _OLVIDAR.search(texto)
    objetivo_previo = ((m.group("x") or m.group("y") or "") if m else "").strip(" .!?¿¡")
    # Solo es "concreto" si queda algo con contenido tras la orden (no
    # "olvida todo" ni "borra la memoria por favor").
    # Palabras que no son un "algo concreto": si solo queda esto tras la orden
    # ("vergiss alles in deinem Gedächtnis", "olvida todo lo de tu memoria"), es
    # borrar todo, no olvidar un dato.
    _relleno = {"todo", "toda", "todos", "everything", "all", "alles", "tout", "lo", "de", "del",
                "en", "in", "tu", "ta", "la", "el", "my", "your", "mi", "deinem", "deine", "que",
                "sabes", "know", "memoria", "memory", "gedächtnis", "mémoire", "please", "por",
                "favor", "porfavor", "hay", "is", "there", "about", "me", "sobre", "mí"}
    _concreto = [w for w in re.findall(r"[a-záéíóúñüäöß]{2,}", objetivo_previo.lower())
                 if w not in _relleno]
    if m and objetivo_previo and _concreto:
        objetivo = re.split(r"[?¿!]|\b(lo odio|i hate it|por favor|please)\b", objetivo_previo)[0].strip(" .,")
        borradas = memory_profile.forget_matching(objetivo) if memory_profile is not None else []
        if memory_store is not None:
            try:
                for rec in await memory_store.list_all():
                    if any(w in (rec.get("content") or "").lower()
                           for w in objetivo.lower().split() if len(w) > 3):
                        await memory_store.delete(rec["id"])
            except Exception as exc:                      # noqa: BLE001
                logger.debug(f"No se pudo filtrar el almacén: {exc}")
        parts.meta["memory_command"] = "forgot"
        if borradas:
            add_notice(parts, "HECHO: se ha olvidado de la memoria de Andromeda: "
                       + "; ".join(borradas) + ". Confírmaselo al usuario brevemente.")
        else:
            add_notice(parts, f"No había nada en la memoria de Andromeda sobre «{objetivo}». "
                       "Díselo al usuario brevemente.")
        diag.log("memory", f"olvidar «{objetivo}»: {len(borradas)} datos",
                 data={"borrados": borradas}, level="success")
        return "forgot"
    if _BORRAR_TODO.search(texto):
        n_perfil = memory_profile.clear_facts() if memory_profile is not None else 0
        n_store = 0
        if memory_store is not None:
            try:
                n_store = await memory_store.clear()
            except Exception as exc:                      # noqa: BLE001
                logger.debug(f"No se pudo vaciar el almacén: {exc}")
        parts.meta["memory_command"] = "cleared"
        add_notice(parts, (
            f"HECHO: la memoria de Andromeda YA SE HA BORRADO ({n_perfil} datos del perfil y "
            f"{n_store or 0} recuerdos). Confírmaselo al usuario en una frase. Las notas que "
            "escribió a mano en Ajustes se han conservado. NO uses ninguna herramienta para esto."))
        diag.log("memory", f"memoria borrada: {n_perfil} datos + {n_store or 0} recuerdos",
                 level="success")
        return "cleared"

    return None



def _resumir_turno(texto: str) -> str:
    """Versión legible de un turno anterior para el historial.

    Los turnos se recortaban tal cual, así que el modelo veía fragmentos como
    `0;\n background: #f4f4f4;` (la mitad de un bloque de código) o llamadas a
    herramientas en JSON. Se sustituyen los bloques de archivo por una nota y
    se eliminan las llamadas: el modelo sabe qué se hizo sin arrastrar el ruido.
    El contenido actual de los archivos ya le llega aparte, completo.
    """
    t = re.sub(r"```andromeda:write\s+path=\"([^\"]+)\".*?(```|$)",
               lambda m: f"[guardó el archivo {m.group(1)}]", texto, flags=re.S)
    t = re.sub(r"<tool_call>.*?(</tool_call>|$)", "", t, flags=re.S)
    t = re.sub(r'\{"tool"\s*:.*?(\}\s*\}|$)', "", t, flags=re.S)
    t = re.sub(r"```[a-zA-Z]*\n.*?(```|$)", "[bloque de código]", t, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", t).strip()



def add_project(parts: PromptParts, request) -> bool:
    """Instrucciones y archivos del proyecto. Devuelve True si hay proyecto."""
    pid = getattr(request, "project_id", None)
    if not pid or getattr(request, "incognito", False):
        return False
    try:
        from app.core.projects import build_context
        bloque = build_context(pid, getattr(request, "project_name", "") or "",
                               getattr(request, "project_instructions", "") or "",
                               getattr(request, "prompt", "") or "")
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"Contexto del proyecto no disponible: {exc}")
        return False
    parts.documents = bloque + (f"\n\n{parts.documents}" if parts.documents else "")
    parts.meta["project_id"] = pid
    diag.log("project", "contexto del proyecto incluido",
             data={"proyecto": pid, "chars": len(bloque)}, detail=bloque[:1500])
    return True



_REMITE = re.compile(
    r"\b(lo que te he dicho|lo que te dije|lo anterior|lo de antes|sobre eso|de eso|sobre esto|"
    r"eso|esto|ello|what i (said|asked)|about (it|that)|that|this|das|dazu|ça|cela)\b",
    re.IGNORECASE)


def _consulta_con_contexto(prompt: str, history: list | None) -> str:
    """Si el mensaje remite a lo anterior, se busca el tema del mensaje previo.

    "por favor busca info sobre lo que te he dicho" buscaba literalmente
    "info sobre lo que te he dicho" (visto en un registro real).
    """
    from app.core.web_search import clean_query
    limpio = clean_query(prompt or "")
    con_contenido = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", limpio)
                     if not _REMITE.fullmatch(w) and w.lower() not in
                     {"info", "información", "informacion", "busca", "buscar", "search", "please",
                      "porfavor", "favor", "sobre", "about", "dicho", "dije", "said"}]
    if history and _REMITE.search(prompt or "") and len(con_contenido) <= 2:
        for m in reversed(history):
            previo = (m.get("content") or "").strip()
            if m.get("role") == "user" and previo and previo != (prompt or "").strip():
                return previo
    return prompt



def add_past_chats(parts: PromptParts, prompt: str, settings, history: list | None,
                   incognito: bool) -> int:
    """"Buscar y consultar conversaciones": si el mensaje remite a una charla
    anterior ("¿recuerdas lo que te dije del coche?"), se buscan los fragmentos
    relevantes en el historial guardado. Antes el interruptor existía en la
    interfaz pero no hacía nada."""
    if incognito or not prompt:
        return 0
    try:
        from app.core.flags import get_flag
        from app.memory import structure as st
        if not get_flag(settings, "andromeda_mem_conversation_search"):
            return 0
        if not st.remite_a_conversaciones(prompt):
            return 0
        from pathlib import Path as _P
        ruta = _P(getattr(settings, "memory_db_path", "data/memory.db")).parent / "ui_state.json"
        excluir = [m.get("content", "") for m in (history or []) if m.get("role") == "user"]
        trozos = st.search_past_chats(ruta, prompt, excluir=excluir + [prompt])
    except Exception as exc:                              # noqa: BLE001
        logger.debug(f"Búsqueda en conversaciones anteriores falló: {exc}")
        return 0
    if not trozos:
        diag.log("memory", "sin coincidencias en conversaciones anteriores")
        return 0
    bloque = "DE CONVERSACIONES ANTERIORES (úsalo si viene al caso):\n" + "\n".join(
        f"- [{t['title'] or 'chat'}] Usuario: {t['user']}\n  Asistente: {_resumir_turno(t['assistant'])[:400]}"
        for t in trozos)
    parts.memory = f"{parts.memory}\n\n{bloque}" if parts.memory else bloque
    diag.log("memory", f"{len(trozos)} fragmentos de conversaciones anteriores",
             detail=bloque[:1200], level="success")
    return len(trozos)



_GENERICA = re.compile(
    r"^\s*[¿¡]?\s*(hola|buenas|hey|hi|hello|hallo|bonjour|你好|gracias|thanks|danke|merci|ok|vale|"
    r"qu[eé] (puedes|sabes) hacer|qu[eé] eres|qui[eé]n eres|c[oó]mo funcionas|ayuda|help|"
    r"what can you do|who are you|what are you|was kannst du|qui es-tu|que peux-tu faire)"
    r"[\s?!.,]*$", re.IGNORECASE)


def es_consulta_generica(prompt: str | None) -> bool:
    """Saludos y preguntas sobre la propia app: no deben traer recuerdos."""
    return bool(_GENERICA.match(prompt or ""))
