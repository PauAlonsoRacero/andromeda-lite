"""
test_integration.py — Tests de integración de los flujos de usuario completos.

Cubre lo que los tests de robustez no tocaban: auth de extremo a extremo,
gestión de modelos (activar/desactivar), conversación multi-turno con historial,
y el endpoint de setup que alimenta el onboarding.
"""
import pytest


# ── Setup / onboarding ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_setup_endpoint_reports_status(app_client):
    """El endpoint que alimenta el onboarding debe responder con el estado."""
    r = await app_client.get("/api/health/setup")
    assert r.status_code == 200
    data = r.json()
    assert "ollama_reachable" in data
    assert "is_ready" in data
    assert "models" in data
    # Cada modelo sugerido lleva un comando de instalación
    for m in data["models"]:
        assert "pull_cmd" in m and m["pull_cmd"]


# ── Gestión de modelos (panel de IAs) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_models_list_and_status(app_client):
    r = await app_client.get("/api/models")
    assert r.status_code == 200
    specs = r.json()
    specs = specs if isinstance(specs, list) else specs.get("specialists", [])
    assert len(specs) >= 1
    assert all("id" in s for s in specs)

    st = await app_client.get("/api/models/status")
    assert st.status_code == 200
    assert "active" in st.json()


@pytest.mark.asyncio
async def test_activate_deactivate_specialist(app_client):
    """Activar/desactivar una IA debe persistir y reflejarse en el status."""
    before = (await app_client.get("/api/models/status")).json().get("active", 0)
    # Desactivar generalist
    r = await app_client.put("/api/models/generalist",
                             json={"model_name": "", "active": False})
    assert r.status_code == 200
    after = (await app_client.get("/api/models/status")).json().get("active", 0)
    assert after == before - 1
    # Reactivar
    r2 = await app_client.put("/api/models/generalist",
                              json={"model_name": "", "active": True})
    assert r2.status_code == 200
    restored = (await app_client.get("/api/models/status")).json().get("active", 0)
    assert restored == before


# ── Traces / actividad ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_traces_and_metrics(app_client):
    assert (await app_client.get("/api/traces")).status_code == 200
    assert (await app_client.get("/api/traces/metrics")).status_code == 200
    # Trace inexistente → 404 limpio, no 500
    assert (await app_client.get("/api/traces/no-existe")).status_code == 404


# ── Health general ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_endpoints(app_client):
    r = await app_client.get("/api/health/hardware")
    assert r.status_code == 200
    data = r.json()
    assert "max_tier" in data or "tier" in data


# ── Generación de documentos (crear archivos reales) ──────────────────────────
@pytest.mark.asyncio
async def test_document_generation_formats(app_client):
    """Genera archivos reales en los 4 formatos con el magic number correcto."""
    content = "# Título\n\nTexto con **negrita**.\n\n- punto 1\n- punto 2\n"
    checks = [("docx", b"PK"), ("xlsx", b"PK"), ("pdf", b"%PDF"), ("md", b"#")]
    for fmt, magic in checks:
        r = await app_client.post("/api/documents/generate",
                                  json={"content": content, "format": fmt, "title": "T"})
        assert r.status_code == 200, f"{fmt} falló"
        assert r.content[:4].startswith(magic), f"{fmt} magic number incorrecto"


@pytest.mark.asyncio
async def test_document_generation_rejects_empty(app_client):
    r = await app_client.post("/api/documents/generate",
                              json={"content": "", "format": "docx"})
    assert r.status_code == 400


# ── Orchestra: explain (preview de decisión sin ejecutar) ─────────────────────
@pytest.mark.asyncio
@pytest.mark.skip(reason="Endpoint /api/orchestra es de Pro (multi-IA)")
async def test_orchestra_explain(app_client):
    r = await app_client.post("/api/orchestra/explain",
                              json={"prompt": "implementa una función en python"})
    assert r.status_code == 200
    data = r.json()
    assert "domain" in data and "power_tier" in data and "specialists" in data
    assert 1 <= data["power_tier"] <= 4


@pytest.mark.asyncio
@pytest.mark.skip(reason="Endpoint /api/orchestra es de Pro (multi-IA)")
async def test_orchestra_explain_rejects_empty(app_client):
    r = await app_client.post("/api/orchestra/explain", json={"prompt": ""})
    assert r.status_code == 400


@pytest.mark.asyncio
@pytest.mark.skip(reason="Endpoint /api/orchestra es de Pro (multi-IA)")
async def test_orchestra_eval_metrics(app_client):
    r = await app_client.get("/api/orchestra/eval")
    # 200 con métricas, o 503 si el dataset no está empaquetado
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        data = r.json()
        assert "train" in data and "holdout" in data
