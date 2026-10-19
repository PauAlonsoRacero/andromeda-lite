"""
memory/store.py — Memoria semántica persistente de Andromeda.

Implementa un vector store ligero usando embeddings de Ollama.
Las memorias se persisten en SQLite con vectores serializados como JSON.

Qué memorias guarda:
  - Fragmentos importantes de conversaciones pasadas
  - Hechos y preferencias del usuario
  - Resultados de herramientas MCP
  - Conocimiento del proyecto indexado

Cómo funciona:
  1. Al finalizar una conversación, se generan embeddings de los mensajes
  2. Los embeddings se guardan en SQLite junto al texto
  3. En cada nueva query, se buscan los K fragmentos más similares
  4. Los fragmentos relevantes se inyectan en el system prompt

Esto da a Andromeda "memoria" entre sesiones sin necesidad de ChromaDB.
SQLite + embeddings JSON es suficiente para ~10K memorias con búsqueda O(n).
Para escalar: migrar a ChromaDB o pgvector (Fase 1 del roadmap).
"""

import json
import math
import re
import logging
import sqlite3
import time
import uuid
from array import array
from pathlib import Path

import httpx

logger = logging.getLogger("andromeda.memory")


# ── Búsqueda rápida: vectores unitarios en caché ─────────────────────────────
# Cada mensaje compara la consulta con TODAS las memorias. Antes se hacía
# json.loads + 3 sumas en Python puro por memoria (~0,2 ms c/u). Ahora cada
# embedding se parsea y normaliza UNA vez, y el producto escalar usa
# math.sumprod (Python ≥3.12; con fallback). Resultado idéntico, ~7× más rápido.
def _sumprod_fallback(a, b):
    return sum(x * y for x, y in zip(a, b))

_SUMPROD = getattr(math, "sumprod", _sumprod_fallback)
_VEC_CACHE: dict = {}
_VEC_CACHE_MAX = 12000


def _dot(a, b) -> float:
    """Producto escalar de dos vectores de igual longitud."""
    return _SUMPROD(a, b)


def _unit(vec) -> "array | None":
    """Vector normalizado a norma 1; None si está vacío.

    Un vector de ceros se devuelve como ceros (no None): el algoritmo original
    lo trataba como semántico con similitud 0.0, no como "sin embedding".
    """
    if not vec:
        return None
    norm = math.sqrt(_SUMPROD(vec, vec))
    if norm == 0:
        return array("d", [0.0] * len(vec))
    return array("d", [x / norm for x in vec])


def _unit_from_text(texto: str) -> "array | None":
    """Parsea un embedding guardado (JSON) y lo devuelve normalizado, con caché.

    La clave es (longitud, hash) del texto: si la memoria cambia, la clave
    cambia. Un JSON roto lanza excepción (la búsqueda salta esa fila).
    """
    key = (len(texto), hash(texto))
    hit = _VEC_CACHE.get(key)
    if hit is not None or key in _VEC_CACHE:
        return hit
    unit = _unit(json.loads(texto))
    if len(_VEC_CACHE) >= _VEC_CACHE_MAX:
        _VEC_CACHE.clear()          # tope simple: nunca crece sin límite
    _VEC_CACHE[key] = unit
    return unit


try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


MEMORY_DB_PATH = "data/memory.db"
EMBED_MODEL    = "nomic-embed-text"   # Modelo de embeddings de Ollama (ligero, ~500MB)
EMBED_DIM      = 768                   # Dimensión de nomic-embed-text
# Con nomic-embed-text y prefijos de tarea, frases relacionadas pero redactadas
# distinto ("¿qué coche me gustaba?" / "Me gusta el Audi TT") suelen puntuar por
# debajo de 0,7: con el umbral anterior (0,72) la búsqueda semántica casi nunca
# devolvía nada. Se combina además con un extra por palabras en común.
SIMILARITY_THRESHOLD = 0.55
# Similitud mínima cuando la pregunta y el recuerdo no comparten ninguna palabra.
SEMANTIC_ONLY_MIN = 0.72
# Versión del modo de cálculo de vectores: si cambia, se recalculan una vez.
EMBED_SCHEME = "nomic-prefix-v1"
# El fallback por texto NO produce valores comparables al coseno: cuenta qué
# fracción de las palabras de la consulta aparece en el recuerdo. Exigirle 0.72
# significa pedir que coincidan casi todas las palabras, y en la práctica no
# devolvía nunca nada cuando Ollama no estaba disponible.
TEXT_MATCH_THRESHOLD = 0.34            # ~1 de cada 3 palabras con contenido


# Cliente HTTP compartido para los embeddings. Se recrea si cambia el bucle de
# eventos (los tests usan uno nuevo en cada asyncio.run).
_cliente = None
_cliente_loop = None


def _cliente_http():
    import asyncio as _asyncio
    global _cliente, _cliente_loop
    loop = _asyncio.get_running_loop()
    if _cliente is None or _cliente_loop is not loop or _cliente.is_closed:
        _cliente = httpx.AsyncClient(trust_env=False)
        _cliente_loop = loop
    return _cliente


class SemanticMemoryStore:
    """
    Vector store ligero sobre SQLite.
    Usa cosine similarity para búsqueda semántica.
    """

    def __init__(self, db_path: str = MEMORY_DB_PATH, ollama_url: str = "http://localhost:11434"):
        self.db_path    = db_path
        self.ollama_url = ollama_url
        self._recover_if_corrupt()   # comprobar integridad ANTES de abrir
        self._init_db()
        self._backup()               # snapshot sano tras iniciar bien
        logger.info(f"MemoryStore iniciado: {db_path}")

    def _backup_path(self) -> Path:
        return Path(self.db_path).with_suffix(".db.bak")

    def _backup(self) -> None:
        """Copia de seguridad de la DB sana (last-known-good)."""
        try:
            src = Path(self.db_path)
            if src.exists() and src.stat().st_size > 0:
                import shutil
                shutil.copy2(src, self._backup_path())
        except Exception as exc:
            logger.debug(f"No se pudo crear backup de memoria: {exc}")

    def _is_corrupt(self) -> bool:
        """True si la DB existe pero no pasa el integrity_check de SQLite."""
        p = Path(self.db_path)
        if not p.exists() or p.stat().st_size == 0:
            return False  # no existe aún → no es corrupción, se creará limpia
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return not (row and row[0] == "ok")
        except sqlite3.DatabaseError:
            return True

    def _recover_if_corrupt(self) -> None:
        """Si la DB está corrupta: restaura del backup, o la archiva y recrea."""
        if not self._is_corrupt():
            return
        logger.error("DB de memoria CORRUPTA — intentando recuperar…")
        bak = self._backup_path()
        if bak.exists() and bak.stat().st_size > 0:
            try:
                import shutil
                shutil.copy2(bak, self.db_path)
                if not self._is_corrupt():
                    logger.info("Memoria restaurada desde backup.")
                    return
            except Exception as exc:
                logger.warning(f"Restore desde backup falló: {exc}")
        # Sin backup válido: archivar la corrupta y empezar limpia (no perder la app)
        try:
            import time as _t
            corrupt_to = Path(self.db_path).with_suffix(f".corrupt-{int(_t.time())}.db")
            Path(self.db_path).rename(corrupt_to)
            logger.warning(f"DB corrupta archivada en {corrupt_to}; se creará una nueva.")
        except Exception as exc:
            logger.warning(f"No se pudo archivar la DB corrupta: {exc}")

    def _init_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id          TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                embedding   TEXT NOT NULL,
                source      TEXT DEFAULT 'chat',
                category    TEXT DEFAULT 'general',
                importance  REAL DEFAULT 0.5,
                created_at  TEXT NOT NULL,
                accessed_at TEXT,
                access_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON memories(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")
        conn.commit()
        conn.close()

    # ── Guardar memoria ──────────────────────────────────────────────────────

    async def save(
        self,
        content: str,
        source: str = "chat",
        category: str = "general",
        importance: float = 0.5,
    ) -> str:
        """Guarda un fragmento de texto como memoria semántica.

        Si el modelo de embeddings de Ollama no está disponible, NO se descarta
        la memoria: se guarda igualmente con embedding vacío y la búsqueda cae a
        coincidencia por texto. Así "Guardar" siempre persiste lo que escribe el
        usuario, esté o no instalado nomic-embed-text.
        """
        if not content.strip():
            return ""

        embedding = await self._embed(content)
        if not embedding:
            logger.warning(
                "Sin modelo de embeddings (nomic-embed-text); guardando memoria "
                "con búsqueda por texto. Instala el modelo para búsqueda semántica."
            )
            embedding = []   # se guarda igual; búsqueda por texto como fallback

        mem_id     = str(uuid.uuid4())
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)",
            (mem_id, content, json.dumps(embedding), source, category,
             importance, created_at, None, 0)
        )
        conn.commit()
        conn.close()

        logger.debug(f"Memoria guardada: {content[:60]}... (id={mem_id[:8]})")
        self._backup()   # snapshot last-known-good tras escribir
        return mem_id

    async def search(
        self,
        query: str,
        k: int = 3,
        category: str | None = None,
        min_similarity: float = SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """
        Busca las K memorias más similares semánticamente a la query.

        Returns:
            Lista de dicts [{id, content, similarity, category, source, ...}]
            ordenados por similitud descendente.
        """
        query_embedding = await self._embed(query, kind="query")

        # Cargar todas las memorias. Dos queries explícitas (sin concatenar SQL)
        # para que el análisis estático no marque falso positivo de inyección.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute("SELECT * FROM memories WHERE category=?", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM memories").fetchall()
        conn.close()

        if not rows:
            return []

        q_lower = (query or "").lower().strip()
        palabras = re.findall(r"\w{4,}", q_lower)       # una vez, no por memoria
        q_unit = _unit(query_embedding) if query_embedding else None
        results = []
        for row in rows:
            try:
                mem_unit = _unit_from_text(row["embedding"]) if row["embedding"] else None
                semantic = bool(q_unit is not None and mem_unit is not None)
                if semantic:
                    # Híbrida: significado + un extra por palabras exactas en común
                    # (nombres propios como "Aritex" que un embedding infravalora).
                    if len(q_unit) != len(mem_unit):
                        sim = 0.0
                    else:
                        sim = _dot(q_unit, mem_unit)
                    texto_m = (row["content"] or "").lower()
                    comunes = sum(1 for w in palabras if w in texto_m)
                    if palabras and comunes:
                        sim = min(1.0, sim + 0.15 * comunes / len(palabras))
                    elif sim < SEMANTIC_ONLY_MIN:
                        # Sin ninguna palabra en común solo cuenta una similitud
                        # alta: con 0,55 entraba "me gusta el color negro" al
                        # preguntar "¿qué puedes hacer?".
                        continue
                else:
                    # Fallback por texto: coincidencia de subcadena / palabras
                    text = (row["content"] or "").lower()
                    if not q_lower:
                        sim = 0.5
                    elif q_lower in text:
                        sim = 0.9
                    else:
                        words = [w for w in q_lower.split() if len(w) > 2]
                        hits = sum(1 for w in words if w in text)
                        sim = (hits / len(words)) if words else 0.0
                # Cada método tiene su propia escala: aplicar el umbral del
                # coseno a un recuento de palabras descarta todo.
                threshold = min_similarity if semantic else min(min_similarity,
                                                                TEXT_MATCH_THRESHOLD)
                if sim >= threshold:
                    results.append({
                        "id":         row["id"],
                        "content":    row["content"],
                        "similarity": round(sim, 3),
                        "category":   row["category"],
                        "source":     row["source"],
                        "importance": row["importance"],
                        "created_at": row["created_at"],
                    })
            except Exception:
                continue

        # Ordenar por similitud * importancia
        results.sort(key=lambda x: x["similarity"] * x["importance"], reverse=True)

        # Métricas de hit rate: cada search cuenta; es "hit" si devolvió algo.
        self._search_count = getattr(self, "_search_count", 0) + 1
        if results:
            self._search_hits = getattr(self, "_search_hits", 0) + 1

        # Actualizar access_count
        if results:
            top_ids = [r["id"] for r in results[:k]]
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn = sqlite3.connect(self.db_path)
            for mid in top_ids:
                conn.execute(
                    "UPDATE memories SET access_count=access_count+1, accessed_at=? WHERE id=?",
                    (now, mid)
                )
            conn.commit()
            conn.close()

        return results[:k]

    def get_stats(self) -> dict:
        """Estadísticas del memory store: total, categorías, fuentes, tamaño
        promedio y hit rate de búsqueda."""
        conn = sqlite3.connect(self.db_path)
        stats = {}
        stats["total"] = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        stats["by_category"] = dict(conn.execute(
            "SELECT category, COUNT(*) FROM memories GROUP BY category"
        ).fetchall())
        stats["by_source"] = dict(conn.execute(
            "SELECT source, COUNT(*) FROM memories GROUP BY source"
        ).fetchall())
        # Tamaño promedio del contenido (caracteres)
        avg = conn.execute("SELECT AVG(LENGTH(content)) FROM memories").fetchone()[0]
        stats["avg_content_chars"] = round(avg, 1) if avg else 0
        # Tamaño total de la DB en disco (KB)
        try:
            stats["db_size_kb"] = round(Path(self.db_path).stat().st_size / 1024, 1)
        except OSError:
            stats["db_size_kb"] = 0
        conn.close()
        # Hit rate de búsqueda (acumulado en memoria desde el arranque)
        searches = getattr(self, "_search_count", 0)
        hits = getattr(self, "_search_hits", 0)
        stats["search_count"] = searches
        stats["search_hit_rate"] = round(hits / searches, 3) if searches else 0.0
        return stats

    async def list_all(self, limit: int = 200) -> list[dict]:
        """Devuelve todas las memorias guardadas, las más recientes primero."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{
            "id":         r["id"],
            "content":    r["content"],
            "category":   r["category"],
            "source":     r["source"],
            "importance": r["importance"],
            "created_at": r["created_at"],
        } for r in rows]

    async def delete(self, memory_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        conn.commit()
        conn.close()
        return True

    async def clear(self) -> int:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.execute("DELETE FROM memories")
        conn.commit()
        conn.close()
        return count

    # ── Helpers internos ─────────────────────────────────────────────────────

    async def purge(self, predicado) -> int:
        """Elimina los recuerdos para los que predicado(texto) es True."""
        n = 0
        for rec in await self.list_all(limit=100000):
            if predicado(rec.get("content") or "") and await self.delete(rec["id"]):
                n += 1
        return n

    async def delete_texts(self, textos: list[str]) -> int:
        """Borra los recuerdos cuyo texto coincide con alguno de estos (normalizado)."""
        norm = lambda t: re.sub(r"[^\w]+", " ", (t or "").lower()).strip()
        objetivos = {norm(t) for t in textos if t}
        return await self.purge(lambda c: norm(c) in objetivos) if objetivos else 0

    def ensure_embed_scheme(self) -> int:
        """Si los vectores se calcularon con otro modo (p. ej. sin prefijos),
        se marcan para recalcular. Devuelve cuántos se marcaron."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
                fila = conn.execute("SELECT value FROM meta WHERE key='embed_scheme'").fetchone()
                if fila and fila[0] == EMBED_SCHEME:
                    return 0
                n = conn.execute("UPDATE memories SET embedding='[]' WHERE embedding NOT IN ('[]','')").rowcount
                conn.execute("INSERT OR REPLACE INTO meta VALUES ('embed_scheme', ?)", (EMBED_SCHEME,))
                return n
        finally:
            conn.close()

    async def backfill_embeddings(self, limite: int = 2000) -> int:
        """Calcula el vector de los recuerdos guardados sin él.

        Los recuerdos creados mientras no había modelo de embeddings se guardan
        con vector vacío y solo se encontraban por palabras. En cuanto el modelo
        está disponible, se completan. Devuelve cuántos se completaron.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            filas = conn.execute(
                "SELECT id, content FROM memories WHERE embedding IN ('[]', '') LIMIT ?",
                (limite,)).fetchall()
        finally:
            conn.close()
        hechos = 0
        for mem_id, contenido in filas:
            vec = await self._embed(contenido)
            if not vec:
                break                                    # el modelo dejó de responder
            conn = sqlite3.connect(self.db_path)
            try:
                with conn:
                    conn.execute("UPDATE memories SET embedding = ? WHERE id = ?",
                                 (json.dumps(vec), mem_id))
            finally:
                conn.close()
            hechos += 1
        return hechos

    async def _embed(self, text: str, kind: str = "document") -> list[float] | None:
        """Genera un embedding usando Ollama.

        Se ejecuta en CADA mensaje, antes de generar la respuesta. Dos mejoras:
          • un solo cliente HTTP reutilizado: crear uno nuevo costaba ~20 ms por
            llamada (httpx prepara un contexto TLS aunque sea localhost);
          • si el modelo de embeddings no está instalado, se deja de preguntar
            durante 5 minutos. Antes se hacía una petición fallida en cada
            mensaje, que además esperaba en cola si Ollama estaba generando.
        """
        import time as _time
        if _time.monotonic() < getattr(self, "_embed_off_until", 0.0):
            return None
        try:
            r = await _cliente_http().post(
                f"{self.ollama_url}/api/embeddings",
                # keep_alive: sin él Ollama descarga el modelo a los 5 min y el
                # siguiente mensaje paga la recarga antes de empezar a responder.
                # nomic-embed-text está entrenado con prefijos de tarea: sin ellos
                # separa peor lo relacionado de lo que no lo es.
                json={"model": EMBED_MODEL,
                      "prompt": (("search_query: " if kind == "query" else "search_document: ")
                                 if EMBED_MODEL.startswith("nomic") else "") + text[:2000],
                      "keep_alive": __import__("os").environ.get("ANDROMEDA_KEEP_ALIVE") or "30m"},
                timeout=10.0,
            )
            if r.status_code == 404:
                # Modelo no instalado: no insistir en un rato.
                self._embed_off_until = _time.monotonic() + 300
                logger.info(f"Modelo de embeddings {EMBED_MODEL} no instalado; "
                            "memoria por palabras clave durante 5 min")
                return None
            r.raise_for_status()
            return r.json().get("embedding")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self._embed_off_until = _time.monotonic() + 30   # Ollama apagado
            logger.debug(f"Embedding no disponible: {exc}")
            return None
        except Exception as exc:
            logger.debug(f"Embedding falló: {exc}")
            return None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity entre dos vectores."""
        if len(a) != len(b):
            return 0.0
        norm_a = math.sqrt(_SUMPROD(a, a))
        norm_b = math.sqrt(_SUMPROD(b, b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return _dot(a, b) / (norm_a * norm_b)

    @staticmethod
    def _classify_category(text: str) -> str:
        """Clasifica el texto en una categoría simple."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["código", "código", "python", "javascript", "función", "bug", "error"]):
            return "code"
        if any(w in text_lower for w in ["docker", "kubernetes", "servidor", "deploy", "nginx"]):
            return "devops"
        if any(w in text_lower for w in ["base de datos", "sql", "postgres", "mongodb"]):
            return "database"
        if any(w in text_lower for w in ["arquitectura", "architecture", "diseño", "patrón", "sistema", "microservice"]):
            return "architecture"
        return "general"

    @staticmethod
    def _estimate_importance(user_msg: str, assistant_msg: str) -> float:
        """Estima la importancia de una memoria (0-1)."""
        score = 0.5
        # Respuestas largas = más información
        if len(assistant_msg) > 1000: score += 0.2
        # Si hay código = probablemente útil
        if "```" in assistant_msg: score += 0.15
        # Si hay links o referencias
        if "http" in assistant_msg: score += 0.05
        return min(score, 1.0)
