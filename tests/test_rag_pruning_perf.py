"""Purga del índice RAG y rendimiento de los endpoints que usa la interfaz."""
import logging
import time
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


# ── P7: purga del índice ───────────────────────────────────────────────────

def test_index_respects_the_document_cap(tmp_path, monkeypatch):
    """Sin tope el índice crece sin fin y, como se carga entero en memoria en
    cada consulta, la app se degrada poco a poco sin explicación."""
    import app.rag.bm25 as bm
    monkeypatch.setattr(bm, "_MAX_DOCUMENTS", 10)
    monkeypatch.setattr(bm, "_MAX_CHUNKS", 100)
    idx = bm.BM25Index(tmp_path / "r.json")
    for i in range(25):
        idx.add_document(f"doc{i}", f"contenido de prueba numero {i} " * 10)
    assert idx.stats()["documents"] <= 10


def test_pruning_keeps_the_documents_actually_used(tmp_path, monkeypatch):
    """Descartar por antigüedad tiraría un manual consultado a diario solo por
    llevar tiempo indexado. Se descarta por uso real."""
    import app.rag.bm25 as bm
    monkeypatch.setattr(bm, "_MAX_DOCUMENTS", 10)
    monkeypatch.setattr(bm, "_MAX_CHUNKS", 100)
    idx = bm.BM25Index(tmp_path / "r.json")

    for i in range(8):
        idx.add_document(f"borrador{i}", f"relleno generico numero {i} " * 10)
    idx.add_document("manual", "El puerto de Andromeda es el 8765 y usa FastAPI")
    for _ in range(5):
        idx.query("puerto andromeda fastapi")        # el manual se consulta mucho

    for i in range(8, 20):
        idx.add_document(f"borrador{i}", f"mas relleno distinto {i} " * 10)

    docs = {c["doc_id"] for c in idx.chunks}
    assert "manual" in docs, "se descartó el documento más consultado"


def test_queries_record_usage(tmp_path):
    from app.rag.bm25 import BM25Index
    idx = BM25Index(tmp_path / "r.json")
    idx.add_document("d", "contenido indexable de prueba")
    idx.query("contenido prueba")
    assert any(c.get("hits", 0) > 0 for c in idx.chunks)


def test_pruning_does_not_trigger_below_the_cap(tmp_path):
    """El uso normal no debe perder nada."""
    from app.rag.bm25 import BM25Index
    idx = BM25Index(tmp_path / "r.json")
    for i in range(20):
        idx.add_document(f"d{i}", f"texto {i}")
    assert idx.stats()["documents"] == 20


# ── Rendimiento de la interfaz ─────────────────────────────────────────────

def test_ui_endpoints_are_fast(tmp_path, monkeypatch):
    """La interfaz consulta el estado cada 3 s: si tarda, todo va lento.

    /api/health tardaba 260 ms porque volvía a sondear TODAS las URLs de Ollama
    en cada petición cuando estaba apagado.
    """
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        for ep in ("/api/health", "/api/models/status", "/api/components"):
            # La primera llamada puede sondear Ollama; se mide a partir de la
            # segunda, que es el caso real: la interfaz consulta cada 3 s.
            c.get(ep)
            c.get(ep)
            t = time.perf_counter()
            for _ in range(3):
                c.get(ep)
            ms = (time.perf_counter() - t) * 1000 / 3
            assert ms < 120, f"{ep} tarda {ms:.0f} ms por petición"


def test_failed_ollama_lookup_is_cached(monkeypatch):
    from app import ollama_resolver
    assert hasattr(ollama_resolver, "_FAILURE_CACHE_S")
    assert ollama_resolver._FAILURE_CACHE_S > 0


# ── Gráficos legibles ──────────────────────────────────────────────────────

def test_large_latencies_are_shown_in_seconds():
    """'107683ms' no se lee de un vistazo; '107.7s' sí."""
    for archivo in ("AnalyticsPanel.jsx", "TraceViewer.jsx"):
        src = (ROOT / "frontend/src/components" / archivo).read_text(encoding="utf-8")
        assert "1000" in src and "toFixed(1)" in src, f"{archivo} no convierte a segundos"
