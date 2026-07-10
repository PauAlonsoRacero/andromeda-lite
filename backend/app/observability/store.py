"""
store.py — Persistencia de traces en SQLite.

Guarda cada TraceRecord en una base de datos SQLite local.
Todas las operaciones son async para no bloquear el event loop de FastAPI.

El schema es simple: una tabla 'traces' con todos los campos del TraceRecord.
Los campos que son listas o dicts se serializan como JSON.

Uso:
    store = TraceStore("data/traces.db")
    await store.init()           # crear tablas si no existen
    await store.save(trace)      # guardar un trace
    records = await store.get_recent(20)  # últimos 20
    stats = await store.get_stats()       # métricas agregadas
"""

import json
import logging
import sqlite3
from pathlib import Path


from app.models.schemas import TraceRecord

logger = logging.getLogger("andromeda.store")


class TraceStore:
    """
    Almacén de traces en SQLite con operaciones async.

    SQLite es perfecto para Fase 0: sin configuración, sin servidor,
    sin dependencias externas. En Fase 1 se migra a PostgreSQL si
    la carga lo justifica.
    """

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Ruta al archivo SQLite (ej: "data/traces.db")
                     Se crea automáticamente si no existe.
        """
        self.db_path = db_path
        # Asegurar que el directorio existe
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        """
        Crea las tablas si no existen.
        Debe llamarse al arranque del servidor (en el lifespan de FastAPI).
        """
        # SQLite no es async nativamente, usamos run_in_executor para no bloquear
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_tables)
        logger.info(f"TraceStore inicializado en '{self.db_path}'")

    def _create_tables(self) -> None:
        """Crea el schema de la base de datos."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # WAL: mejor rendimiento en concurrent writes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id            TEXT PRIMARY KEY,
                request_id          TEXT NOT NULL,
                timestamp           TEXT NOT NULL,
                prompt_preview      TEXT DEFAULT '',
                strategy            TEXT DEFAULT '',
                strategy_effective  TEXT DEFAULT '',
                specialists_used    TEXT DEFAULT '[]',  -- JSON array
                degraded            INTEGER DEFAULT 0,   -- SQLite no tiene BOOLEAN
                degradation_reason  TEXT,
                latency_ms          REAL DEFAULT 0,
                ttft_ms             REAL DEFAULT 0,
                hardware_tier       INTEGER DEFAULT 1,
                vram_free_gb        REAL DEFAULT 0,
                policy_applied      TEXT DEFAULT '',
                classifier_source   TEXT DEFAULT 'keywords',
                classifier_confidence REAL DEFAULT 0,
                routing_reasoning   TEXT DEFAULT '',
                success             INTEGER NOT NULL,    -- 0 o 1
                error               TEXT,
                spans               TEXT DEFAULT '[]',   -- JSON array
                created_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Índices para las consultas más frecuentes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON traces(timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_request_id ON traces(request_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_success ON traces(success)")
        conn.commit()
        conn.close()

    async def save(self, trace: TraceRecord) -> None:
        """
        Guarda un TraceRecord en la base de datos.
        Operación async — no bloquea el event loop.

        Si hay un error al guardar, lo registra en el log pero
        NO lanza excepción (la observabilidad no debe romper el sistema).
        """
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._insert_trace, trace)
        except Exception as exc:
            # La observabilidad falla silenciosamente — el sistema sigue operando
            logger.error(f"Error al guardar trace {trace.trace_id}: {exc}")

    def _insert_trace(self, trace: TraceRecord) -> None:
        """Inserción síncrona en SQLite (ejecutada en thread pool)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO traces (
                    trace_id, request_id, timestamp, prompt_preview,
                    strategy, strategy_effective, specialists_used,
                    degraded, degradation_reason, latency_ms, ttft_ms,
                    hardware_tier, vram_free_gb, policy_applied,
                    classifier_source, classifier_confidence,
                    routing_reasoning, success, error, spans
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                trace.request_id,
                trace.timestamp,
                trace.prompt_preview[:100],  # Máx 100 chars por privacidad
                trace.strategy,
                trace.strategy_effective,
                json.dumps(trace.specialists_used),
                int(trace.degraded),
                trace.degradation_reason,
                trace.latency_ms,
                trace.ttft_ms,
                trace.hardware_tier,
                trace.vram_free_gb,
                trace.policy_applied,
                trace.classifier_source,
                trace.classifier_confidence,
                trace.routing_reasoning,
                int(trace.success),
                trace.error,
                json.dumps(trace.spans),
            ))
            conn.commit()

            # Mantener solo los últimos N traces (rotación automática)
            conn.execute("""
                DELETE FROM traces
                WHERE trace_id NOT IN (
                    SELECT trace_id FROM traces
                    ORDER BY timestamp DESC
                    LIMIT 200
                )
            """)
            conn.commit()
        finally:
            conn.close()

    async def get_recent(self, limit: int = 20) -> list[dict]:
        """
        Retorna los últimos N traces ordenados por timestamp descendente.

        Args:
            limit: Número máximo de traces a retornar (default 20)

        Returns:
            Lista de dicts con los datos de cada trace
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_recent, limit)

    def _fetch_recent(self, limit: int) -> list[dict]:
        """Consulta síncrona a SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acceder por nombre de columna
        try:
            cursor = conn.execute("""
                SELECT * FROM traces
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    async def get_by_request_id(self, request_id: str) -> dict | None:
        """
        Busca el trace de un request específico por su request_id.

        Returns:
            Dict del trace o None si no existe
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_by_request, request_id)

    def _fetch_by_request(self, request_id: str) -> dict | None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM traces WHERE request_id = ? LIMIT 1",
                (request_id,)
            )
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    async def get_stats(self) -> dict:
        """
        Calcula estadísticas agregadas para el endpoint /api/traces/metrics.

        Returns:
            Dict con: total_requests, success_rate, avg_latency_ms,
                      p95_latency_ms, most_used_strategy, degradation_rate,
                      specialist_distribution, strategy_distribution
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._calculate_stats)

    def _calculate_stats(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        try:
            # Total y success rate
            total = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
            if total == 0:
                return {"total_requests": 0, "message": "Sin traces aún"}

            successful = conn.execute("SELECT COUNT(*) FROM traces WHERE success=1").fetchone()[0]

            # Latencias
            latencies = [
                row[0] for row in
                conn.execute("SELECT latency_ms FROM traces WHERE latency_ms > 0 ORDER BY latency_ms").fetchall()
            ]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            p95_idx = int(len(latencies) * 0.95)
            p95_latency = latencies[p95_idx] if latencies else 0

            # Estrategia más usada
            strategy_row = conn.execute("""
                SELECT strategy_effective, COUNT(*) as cnt
                FROM traces
                GROUP BY strategy_effective
                ORDER BY cnt DESC
                LIMIT 1
            """).fetchone()

            # Degradaciones
            degraded = conn.execute("SELECT COUNT(*) FROM traces WHERE degraded=1").fetchone()[0]

            # Distribución de estrategias
            strategy_rows = conn.execute("""
                SELECT strategy_effective, COUNT(*) as cnt
                FROM traces
                GROUP BY strategy_effective
            """).fetchall()

            # Distribución de especialistas (parseando el JSON de specialists_used)
            all_specialists_rows = conn.execute(
                "SELECT specialists_used FROM traces"
            ).fetchall()
            specialist_counts: dict = {}
            for row in all_specialists_rows:
                try:
                    specs = json.loads(row[0] or "[]")
                    for s in specs:
                        specialist_counts[s] = specialist_counts.get(s, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass

            return {
                "total_requests": total,
                "success_rate_pct": round(successful / total * 100, 1),
                "avg_latency_ms": round(avg_latency, 0),
                "p95_latency_ms": round(p95_latency, 0),
                "degradation_rate_pct": round(degraded / total * 100, 1),
                "most_used_strategy": strategy_row[0] if strategy_row else "N/A",
                "strategy_distribution": {row[0]: row[1] for row in strategy_rows},
                "specialist_distribution": specialist_counts,
            }
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convierte una fila SQLite a dict, deserializando los campos JSON."""
        d = dict(row)
        # Deserializar campos JSON
        for field in ("specialists_used", "spans"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
        # Convertir 0/1 a bool
        d["degraded"] = bool(d.get("degraded", 0))
        d["success"] = bool(d.get("success", 1))
        return d

    async def search_traces(self, query: str, limit: int = 20) -> list[dict]:
        """Busca traces por texto en prompt_preview o specialist."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            q = f"%{query.lower()}%"
            cursor = conn.execute("""
                SELECT request_id, prompt_preview, strategy_effective,
                       specialists_used, latency_ms, success, timestamp
                FROM traces
                WHERE LOWER(prompt_preview) LIKE ? OR LOWER(strategy_effective) LIKE ?
                ORDER BY timestamp DESC LIMIT ?
            """, (q, q, limit))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()
