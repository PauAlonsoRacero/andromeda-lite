"""Microbenchmark: búsqueda de memoria, algoritmo original vs. optimizado.

Uso:  python benchmarks/microbench.py
No necesita Ollama: usa embeddings sintéticos (768 dim, como nomic-embed-text).
Mide solo la parte de CPU que se repite en cada mensaje del chat.
"""
import asyncio
import json
import random
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.memory import store as S  # noqa: E402

DIM = 768


def cos_orig(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def search_orig(rows, query, qemb):
    q = query.lower()
    out = []
    for r in rows:
        mem = json.loads(r["embedding"])
        sim = cos_orig(qemb, mem)
        txt = r["content"].lower()
        pal = re.findall(r"\w{4,}", q)
        com = sum(1 for w in pal if w in txt)
        if pal and com:
            sim = min(1.0, sim + 0.15 * com / len(pal))
        elif sim < S.SEMANTIC_ONLY_MIN:
            continue
        if sim >= S.SIMILARITY_THRESHOLD:
            out.append((r["id"], sim))
    return out


async def main():
    rng = random.Random(0)
    print(f"{'memorias':>9} {'original':>10} {'optimizado':>11} {'mejora':>7}")
    for n in (500, 2000, 5000):
        with tempfile.TemporaryDirectory() as d:
            st = S.SemanticMemoryStore(db_path=str(Path(d) / "m.db"))
            conn = sqlite3.connect(st.db_path)
            cols = [c[1] for c in conn.execute("PRAGMA table_info(memories)")]
            for i in range(n):
                v = {"id": f"m{i}", "content": f"recuerdo {i} aritex",
                     "embedding": json.dumps([rng.uniform(-1, 1) for _ in range(DIM)]),
                     "category": "general", "source": "bench", "importance": 0.5,
                     "created_at": "2026-01-01", "accessed_at": "2026-01-01",
                     "access_count": 0}
                use = [c for c in cols if c in v]
                conn.execute(f"INSERT INTO memories ({','.join(use)}) "
                             f"VALUES ({','.join('?' * len(use))})", [v[c] for c in use])
            conn.commit()
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM memories").fetchall()
            conn.close()

            qemb = [rng.uniform(-1, 1) for _ in range(DIM)]

            async def fake(self, text, kind="document"):
                return qemb
            S.SemanticMemoryStore._embed = fake

            t0 = time.perf_counter(); search_orig(rows, "aritex", qemb)
            t_orig = time.perf_counter() - t0

            S._VEC_CACHE.clear()
            await st.search("aritex")                      # 1.ª vez: fría
            t0 = time.perf_counter(); await st.search("aritex")
            t_new = time.perf_counter() - t0
            print(f"{n:>9} {t_orig*1000:>8.1f}ms {t_new*1000:>9.1f}ms {t_orig/t_new:>6.1f}×")


asyncio.run(main())
