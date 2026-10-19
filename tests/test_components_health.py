"""Monitorización de cada subsistema de Andromeda."""
import logging

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def test_reports_all_components(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        d = c.get("/api/components").json()
        # 'specialists' solo aparece en Pro: en Lite hay un único modelo y la
        # tarjeta describiría algo que no existe en esta edición.
        expected = {"ollama", "memory", "rag", "skills", "mcp",
                    "web_search", "registry", "ab_testing", "feedback", "workspace"}
        assert expected <= set(d["components"])
        assert d["total"] == len(d["components"])


def test_every_component_has_status_metric_and_detail(tmp_path, monkeypatch):
    """El detalle es lo que le dice al usuario qué hacer: nunca puede faltar."""
    with _client(tmp_path, monkeypatch) as c:
        for name, comp in c.get("/api/components").json()["components"].items():
            assert comp["status"] in ("ok", "degraded", "off", "error"), name
            assert comp["metric"], name
            # El detalle viaja como clave i18n para que la UI pueda traducirlo.
            assert comp.get("detail_key") or comp.get("detail"), name


def test_details_are_translatable_keys(tmp_path, monkeypatch):
    """Los textos no pueden ir fijos en un idioma desde el backend."""
    with _client(tmp_path, monkeypatch) as c:
        comps = c.get("/api/components").json()["components"]
        keyed = [x for x in comps.values() if x.get("detail_key")]
        assert len(keyed) == len(comps)
        for x in keyed:
            assert x["detail_key"].startswith("cd.")


def test_healthy_count_matches_ok_components(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        d = c.get("/api/components").json()
        assert d["healthy"] == sum(1 for x in d["components"].values() if x["status"] == "ok")


def test_rag_reflects_indexed_documents(tmp_path, monkeypatch):
    """Un componente debe reflejar cambios reales de estado, no valores fijos."""
    with _client(tmp_path, monkeypatch) as c:
        before = c.get("/api/components").json()["components"]["rag"]["status"]
        doc_id = "componente-health-probe"          # id propio: no contamina otros tests
        c.post("/api/rag/documents", json={"id": doc_id, "text": "contenido de prueba"})
        try:
            rag = c.get("/api/components").json()["components"]["rag"]
            assert rag["status"] == "ok"
            assert before in ("off", "ok")
        finally:
            c.delete(f"/api/rag/documents/{doc_id}")   # se limpia siempre


def test_skills_component_counts_catalog(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        sk = c.get("/api/components").json()["components"]["skills"]
        assert sk["status"] == "ok"
        assert "9" in sk["metric"] or "skills" in sk["metric"]


def test_probe_failure_is_isolated(tmp_path, monkeypatch):
    """Si una sonda revienta, las demás deben seguir respondiendo."""
    from app.routes import components_health as ch

    def boom():
        raise RuntimeError("fallo simulado")

    out = ch._probe(boom)
    assert out["status"] == "error"
    assert "fallo simulado" in str(out.get("detail_args", {}))


def test_endpoint_is_fast(tmp_path, monkeypatch):
    """Se consulta al abrir el panel: no puede bloquear la interfaz."""
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/components").json()["probe_ms"] < 2000
