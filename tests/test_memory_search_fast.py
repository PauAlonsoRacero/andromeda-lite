"""Búsqueda de memoria optimizada: mismo resultado que el algoritmo original.

La optimización (vectores unitarios en caché + math.sumprod) NO puede cambiar
qué recuerdos salen ni en qué orden. Aquí el algoritmo original está copiado
como referencia y se compara contra el real.
"""
import json
import math
import random
import re
import sqlite3
import time

import pytest

from app.memory import store as S


# ── Referencia: el algoritmo ORIGINAL (antes de optimizar) ───────────────────
def _cos_orig(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _search_orig(rows, query, qemb, k=3, min_similarity=S.SIMILARITY_THRESHOLD):
    q_lower = (query or "").lower().strip()
    out = []
    for row in rows:
        try:
            mem = json.loads(row["embedding"]) if row["embedding"] else []
            semantic = bool(qemb and mem)
            if semantic:
                sim = _cos_orig(qemb, mem)
                texto = (row["content"] or "").lower()
                palabras = re.findall(r"\w{4,}", q_lower)
                comunes = sum(1 for w in palabras if w in texto)
                if palabras and comunes:
                    sim = min(1.0, sim + 0.15 * comunes / len(palabras))
                elif sim < S.SEMANTIC_ONLY_MIN:
                    continue
            else:
                texto = (row["content"] or "").lower()
                if not q_lower:
                    sim = 0.5
                elif q_lower in texto:
                    sim = 0.9
                else:
                    words = [w for w in q_lower.split() if len(w) > 2]
                    hits = sum(1 for w in words if w in texto)
                    sim = (hits / len(words)) if words else 0.0
            thr = min_similarity if semantic else min(min_similarity, S.TEXT_MATCH_THRESHOLD)
            if sim >= thr:
                out.append((row["id"], round(sim, 3), row["importance"]))
        except Exception:
            continue
    out.sort(key=lambda x: x[1] * x[2], reverse=True)
    return [(i, s) for i, s, _ in out[:k]]


# ── Utilidades ───────────────────────────────────────────────────────────────
DIM = 64


def _vec(rng, dim=DIM):
    return [rng.uniform(-1, 1) for _ in range(dim)]


def _near(rng, base, noise):
    return [x + rng.uniform(-noise, noise) for x in base]


@pytest.fixture(autouse=True)
def _limpia_cache():
    S._VEC_CACHE.clear()
    yield
    S._VEC_CACHE.clear()


@pytest.fixture
def store(tmp_path):
    return S.SemanticMemoryStore(db_path=str(tmp_path / "memory.db"))


def _rows(store):
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM memories").fetchall()
    conn.close()
    return r


def _insert(store, content, emb, importance=0.5, category="general"):
    """Inserta una fila directamente (sin pasar por Ollama)."""
    mid = f"m{abs(hash((content, str(emb)[:40]))) % 10**9}-{random.random()}"
    conn = sqlite3.connect(store.db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)")]
    vals = {
        "id": mid, "content": content, "embedding": emb,
        "category": category, "source": "test", "importance": importance,
        "created_at": "2026-01-01T00:00:00Z", "accessed_at": "2026-01-01T00:00:00Z",
        "access_count": 0,
    }
    use = [c for c in cols if c in vals]
    conn.execute(
        f"INSERT INTO memories ({','.join(use)}) VALUES ({','.join('?' * len(use))})",
        [vals[c] for c in use])
    conn.commit()
    conn.close()
    return mid


def _poblar(store, n, seed=1):
    rng = random.Random(seed)
    topics = [_vec(rng) for _ in range(8)]
    palabras = ["aritex", "badalona", "python", "monlau", "suiza", "bitcoin",
                "ollama", "docker", "madrid", "invertir"]
    for i in range(n):
        t = rng.choice(topics)
        txt = f"recuerdo {i} sobre {rng.choice(palabras)} y {rng.choice(palabras)}"
        _insert(store, txt, json.dumps(_near(rng, t, 0.35)),
                importance=rng.choice([0.3, 0.5, 0.8, 1.0]))
    return rng, topics


async def _buscar(store, monkeypatch, query, qemb, **kw):
    async def fake_embed(self, text, kind="document"):
        return qemb
    monkeypatch.setattr(S.SemanticMemoryStore, "_embed", fake_embed)
    res = await store.search(query, **kw)
    return [(r["id"], r["similarity"]) for r in res]


# ── Equivalencia ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_mismo_resultado_que_el_algoritmo_original(store, monkeypatch, seed):
    rng, topics = _poblar(store, 300, seed)
    for q in ["qué sé de aritex", "badalona python", "hola", "invertir en bitcoin"]:
        qemb = _near(rng, rng.choice(topics), 0.2)
        esperado = _search_orig(_rows(store), q, qemb, k=5)
        real = await _buscar(store, monkeypatch, q, qemb, k=5)
        assert [i for i, _ in real] == [i for i, _ in esperado]
        for (_, a), (_, b) in zip(real, esperado):
            assert a == pytest.approx(b, abs=1e-3)


async def test_consulta_sin_embedding_usa_texto_como_antes(store, monkeypatch):
    _insert(store, "trabajo en Aritex como becario", "")
    _insert(store, "me gusta el color negro", "")
    esperado = _search_orig(_rows(store), "aritex becario", None)
    real = await _buscar(store, monkeypatch, "aritex becario", None)
    assert [i for i, _ in real] == [i for i, _ in esperado] and real


async def test_filtro_por_categoria_se_mantiene(store, monkeypatch):
    rng = random.Random(9)
    base = _vec(rng)
    a = _insert(store, "dato de trabajo aritex", json.dumps(base), category="trabajo")
    _insert(store, "dato personal aritex", json.dumps(base), category="personal")
    res = await _buscar(store, monkeypatch, "aritex", base, category="trabajo")
    assert [i for i, _ in res] == [a]


async def test_dimensiones_distintas_dan_similitud_cero(store, monkeypatch):
    rng = random.Random(3)
    _insert(store, "texto sin relación alguna", json.dumps(_vec(rng, 32)))
    res = await _buscar(store, monkeypatch, "otra cosa", _vec(rng, 64))
    assert res == []   # sim 0.0 < umbral, igual que el original


async def test_vector_de_ceros_es_semantico_con_similitud_cero(store, monkeypatch):
    """Como el original: ceros → semántico con sim 0.0 (no cae al modo texto)."""
    _insert(store, "aritex aritex aritex", json.dumps([0.0] * DIM))
    esperado = _search_orig(_rows(store), "aritex", [0.5] * DIM)
    real = await _buscar(store, monkeypatch, "aritex", [0.5] * DIM)
    assert real == esperado


async def test_fila_con_json_roto_se_salta_sin_romper(store, monkeypatch):
    rng = random.Random(4)
    base = _vec(rng)
    ok = _insert(store, "recuerdo valido aritex", json.dumps(base))
    _insert(store, "recuerdo roto aritex", "{esto no es json")
    res = await _buscar(store, monkeypatch, "aritex", base)
    assert [i for i, _ in res] == [ok]


# ── Caché ────────────────────────────────────────────────────────────────────
def test_unit_devuelve_norma_uno_y_none_si_vacio():
    u = S._unit([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in u)), 1.0)
    assert S._unit([]) is None


def test_cache_parsea_una_sola_vez(monkeypatch):
    llamadas = []
    real_loads = json.loads
    monkeypatch.setattr(S.json, "loads", lambda t: (llamadas.append(1), real_loads(t))[1])
    txt = json.dumps([1.0, 2.0, 3.0])
    a = S._unit_from_text(txt)
    b = S._unit_from_text(txt)
    assert a is b and len(llamadas) == 1


def test_cache_distingue_embeddings_distintos():
    a = S._unit_from_text(json.dumps([1.0, 0.0]))
    b = S._unit_from_text(json.dumps([0.0, 1.0]))
    assert list(a) != list(b)


def test_cache_tiene_tope(monkeypatch):
    monkeypatch.setattr(S, "_VEC_CACHE_MAX", 50)
    for i in range(500):
        S._unit_from_text(json.dumps([float(i + 1), 1.0]))
    assert len(S._VEC_CACHE) <= 50


def test_json_roto_no_se_cachea():
    with pytest.raises(Exception):
        S._unit_from_text("{roto")
    assert not S._VEC_CACHE


async def test_memoria_editada_no_usa_vector_viejo(store, monkeypatch):
    rng = random.Random(5)
    v1, v2 = _vec(rng), _vec(rng)
    mid = _insert(store, "aritex nota", json.dumps(v1))
    assert await _buscar(store, monkeypatch, "aritex", v1)
    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE memories SET embedding=? WHERE id=?", (json.dumps(v2), mid))
    conn.commit(); conn.close()
    nuevo = await _buscar(store, monkeypatch, "aritex", v2)
    esperado = _search_orig(_rows(store), "aritex", v2)
    assert nuevo == esperado


# ── _cosine_similarity sigue siendo correcta ─────────────────────────────────
def test_cosine_casos_basicos():
    c = S.SemanticMemoryStore._cosine_similarity
    assert c([1, 0], [1, 0]) == pytest.approx(1.0)
    assert c([1, 0], [0, 1]) == pytest.approx(0.0)
    assert c([1, 0], [1, 0, 0]) == 0.0
    assert c([0, 0], [1, 1]) == 0.0


def test_fallback_sin_sumprod_da_lo_mismo():
    a, b = [0.1, 0.2, 0.3], [0.4, 0.5, 0.6]
    assert S._sumprod_fallback(a, b) == pytest.approx(S._SUMPROD(a, b))


# ── Rendimiento ──────────────────────────────────────────────────────────────
# Un test de "es N veces más rápido" con tiempos reales es frágil: en los servidores
# de CI falla de forma intermitente (pasó en los tres sistemas). Lo que hace rápida
# la búsqueda es no volver a parsear cada embedding, y eso se comprueba contando
# llamadas, que es determinista. La medición de tiempos queda en un test `slow` y en
# benchmarks/microbench.py.
async def test_segunda_busqueda_no_vuelve_a_parsear_embeddings(store, monkeypatch):
    rng, topics = _poblar(store, 300, 11)
    qemb = _near(rng, topics[0], 0.2)
    llamadas = []
    real_loads = json.loads
    monkeypatch.setattr(S.json, "loads",
                        lambda t, *a, **k: (llamadas.append(1), real_loads(t, *a, **k))[1])

    await _buscar(store, monkeypatch, "badalona python", qemb)
    assert len(llamadas) == 300          # primera vez: una lectura por recuerdo

    llamadas.clear()
    await _buscar(store, monkeypatch, "badalona python", qemb)
    await _buscar(store, monkeypatch, "invertir bitcoin", qemb)
    assert llamadas == []                # después: ninguna, todo sale de la caché


@pytest.mark.slow
async def test_es_mas_rapido_que_el_original_con_embeddings_reales(store, monkeypatch):
    """Medición de tiempos (solo a mano: pytest -m slow). Usa 768 dimensiones."""
    rng = random.Random(11)
    base = _vec(rng, 768)
    for i in range(2000):
        _insert(store, f"recuerdo {i} badalona", json.dumps(_near(rng, base, 0.4)))
    qemb = _near(rng, base, 0.2)
    rows = _rows(store)
    await _buscar(store, monkeypatch, "badalona", qemb)      # calienta la caché

    def mejor(fn, n=3):
        ts = []
        for _ in range(n):
            t = time.perf_counter(); fn(); ts.append(time.perf_counter() - t)
        return min(ts)

    t_orig = mejor(lambda: _search_orig(rows, "badalona", qemb))
    ts = []
    for _ in range(3):
        t = time.perf_counter()
        await store.search("badalona")
        ts.append(time.perf_counter() - t)
    assert t_orig / min(ts) >= 2, (t_orig, min(ts))
