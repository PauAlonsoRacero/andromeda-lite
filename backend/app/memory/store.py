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
import logging
import sqlite3
import time
import uuid
from pathlib import Path

import httpx

logger = logging.getLogger("andromeda.memory")

MEMORY_DB_PATH = "data/memory.db"
EMBED_MODEL    = "nomic-embed-text"   # Modelo de embeddings de Ollama (ligero, ~500MB)
EMBED_DIM      = 768                   # Dimensión de nomic-embed-text
SIMILARITY_THRESHOLD = 0.72            # Mínimo cosine similarity para considerar relevante


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

    async def save_conversation_turn(
        self,
        user_msg: str,
        assistant_msg: str,
        metadata: dict | None = None,
    ) -> list[str]:
        """
        Guarda un turno de conversación como memorias.
        Solo guarda fragmentos con información factual, no saludos ni trivialidades.
        """
        saved = []
        # Solo guardar si la respuesta es sustancial
        if len(assistant_msg) > 100:
            # Guardar la respuesta del asistente como memoria
            mem_id = await self.save(
                content=f"Q: {user_msg[:200]}\nA: {assistant_msg[:500]}",
                source="conversation",
                category=self._classify_category(user_msg),
                importance=self._estimate_importance(user_msg, assistant_msg),
            )
            if mem_id:
                saved.append(mem_id)
        return saved

    # ── Buscar memorias relevantes ───────────────────────────────────────────

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
        query_embedding = await self._embed(query)

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
        results = []
        for row in rows:
            try:
                mem_embedding = json.loads(row["embedding"]) if row["embedding"] else []
                if query_embedding and mem_embedding:
                    # Búsqueda semántica
                    sim = self._cosine_similarity(query_embedding, mem_embedding)
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
                if sim >= min_similarity:
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

    def build_memory_context(self, memories: list[dict]) -> str:
        """Construye el bloque de contexto de memoria para inyectar en el system prompt."""
        if not memories:
            return ""
        lines = ["MEMORIAS RELEVANTES DE CONVERSACIONES ANTERIORES:"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"{i}. [{mem['category']}] {mem['content'][:300]}")
        lines.append("(Usa estas memorias como contexto adicional si son relevantes.)")
        return "\n".join(lines)

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

    async def _embed(self, text: str) -> list[float] | None:
        """Genera un embedding usando Ollama."""
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                r = await client.post(
                    f"{self.ollama_url}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": text[:2000]},
                    timeout=10.0,
                )
                r.raise_for_status()
                return r.json().get("embedding")
        except Exception as exc:
            logger.debug(f"Embedding falló: {exc}")
            return None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity entre dos vectores."""
        if len(a) != len(b):
            return 0.0
        dot   = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

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
