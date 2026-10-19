"""Latencia (keep_alive) y qué componentes muestra cada edición."""
import logging

logging.disable(logging.CRITICAL)


# ── Latencia ───────────────────────────────────────────────────────────────

def test_requests_keep_the_model_loaded():
    """Sin keep_alive, Ollama descarga el modelo a los 5 minutos y la siguiente
    pregunta paga la recarga completa: decenas de segundos con un 14-27B. Es la
    causa principal de que el p95 se dispare con el p50 aparentemente bien."""
    import inspect
    from app.core import executor, streaming
    for mod, nombre in ((streaming, "streaming.py"), (executor, "executor.py")):
        assert "keep_alive" in inspect.getsource(mod), f"{nombre} no fija keep_alive"


def test_keep_alive_default_and_override(monkeypatch):
    from app.core.streaming import _keep_alive
    monkeypatch.delenv("ANDROMEDA_KEEP_ALIVE", raising=False)
    assert _keep_alive() == "30m"
    monkeypatch.setenv("ANDROMEDA_KEEP_ALIVE", "-1")
    assert _keep_alive() == "-1"          # indefinido, para equipos con VRAM libre


# ── Componentes según la edición ───────────────────────────────────────────

def test_specialists_hidden_in_lite(tmp_path, monkeypatch):
    """'Especialistas' es un concepto de Pro (varias IAs en paralelo). En Lite
    hay un solo modelo, así que la tarjeta solo confunde."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    from app.editions import orchestration_enabled
    with TestClient(create_app()) as c:
        comps = c.get("/api/components").json()["components"]
        if orchestration_enabled():
            assert "specialists" in comps
        else:
            assert "specialists" not in comps


def test_component_count_matches_what_is_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        d = c.get("/api/components").json()
        assert d["total"] == len(d["components"])


# ── El panel se monta una sola vez ────────────────────────────────────────

def test_components_panel_is_not_inside_a_repeated_element():
    """El bug: quedó dentro del subcomponente de tarjeta métrica, que se
    renderiza una vez por métrica, y aparecía triplicado y solapado."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "frontend/src/components/AnalyticsPanel.jsx").read_text(encoding="utf-8")
    assert src.count("<ComponentsHealth />") == 1
    # debe estar en el componente principal, junto a QualitySLO
    pos_panel = src.index("<ComponentsHealth />")
    pos_slo = src.index("<QualitySLO />")
    pos_sub = src.index("// ── Subcomponentes")
    assert pos_slo < pos_panel < pos_sub, "el panel está en un subcomponente"


def test_percentiles_are_explained():
    """p50/p95/p99 no significan nada para quien no los conoce."""
    from pathlib import Path
    i18n = (Path(__file__).resolve().parent.parent
            / "frontend/src/stores/i18n.js").read_text(encoding="utf-8")
    for k in ("info.pct.p50h", "info.pct.p95h", "info.pct.p99h"):
        assert f"'{k}'" in i18n, f"falta la explicación {k}"
