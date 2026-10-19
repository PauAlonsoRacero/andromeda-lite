"""RAG local (BM25): indexado, consulta, persistencia y API."""


def test_bm25_index_and_query(tmp_path):
    from app.rag.bm25 import BM25Index
    idx = BM25Index(tmp_path / "rag.json")
    idx.add_document("arq", "Andromeda usa FastAPI en el backend y SolidJS en el frontend.")
    idx.add_document("cocina", "Receta de paella: arroz, azafrán y caldo.")
    hits = idx.query("qué framework usa el backend", k=2)
    assert hits and hits[0]["doc_id"] == "arq"


def test_bm25_persistence_roundtrip(tmp_path):
    from app.rag.bm25 import BM25Index
    p = tmp_path / "rag.json"
    BM25Index(p).add_document("d1", "kubernetes despliega contenedores en un clúster")
    idx2 = BM25Index(p)
    assert idx2.stats()["documents"] == 1
    assert idx2.query("clúster de contenedores")[0]["doc_id"] == "d1"


def test_bm25_remove_and_empty_safe(tmp_path):
    from app.rag.bm25 import BM25Index
    idx = BM25Index(tmp_path / "rag.json")
    idx.add_document("d1", "texto sobre observabilidad y métricas")
    assert idx.remove_document("d1") >= 1
    assert idx.query("observabilidad") == []
    assert idx.stats()["chunks"] == 0


def test_rag_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.post("/api/rag/documents",
                   json={"id": "notas", "text": "El registry promueve modelos a producción."})
        assert r.status_code == 200 and r.json()["indexed"]
        # El índice puede contener documentos de otras pruebas: se comprueba que
        # el nuestro está y es el más relevante para SU consulta, no que sea el único.
        top = c.get("/api/rag/query", params={"q": "promover a producción"}).json()["results"]
        assert top and top[0]["doc_id"] == "notas"
        listed = {d["id"] for d in c.get("/api/rag/documents").json()["documents"]}
        assert "notas" in listed
        c.delete("/api/rag/documents/notas")
        assert "notas" not in {d["id"] for d in
                               c.get("/api/rag/documents").json()["documents"]}
