"""Evitar invención de datos actuales, y textos/métricas correctos en la interfaz."""
import logging
import re
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


# ── El modelo inventaba datos actuales ─────────────────────────────────────

def test_asking_about_a_changing_entity_triggers_search():
    """Caso real: "about minecraft" no disparaba búsqueda, y el modelo inventó
    versiones, biomas y criaturas de 2026 con total seguridad."""
    from app.core.web_search import needs_web_search
    for p in ("about minecraft", "tell me about minecraft", "háblame de minecraft",
              "qué es react", "cuéntame sobre windows", "info sobre el iphone"):
        assert needs_web_search(p), f"no buscaría para: {p!r}"


def test_timeless_questions_still_dont_search():
    """Buscar de más también es un problema: gasta tiempo y contexto."""
    from app.core.web_search import needs_web_search
    for p in ("explain pointers in C", "explícame la recursividad",
              "escríbeme un poema sobre el mar", "cuánto es 2+2", "hola qué tal"):
        assert not needs_web_search(p), f"buscaría innecesariamente para: {p!r}"


def test_system_prompt_forbids_inventing_current_data(monkeypatch):
    """Cuando no hay datos frescos, el modelo debe decirlo, no rellenar."""
    from app.specialists.identity import with_identity
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "en")
    out = with_identity("x", "generalist", "gemma3:27b", user_prompt="about minecraft")
    assert "CHANGING FACTS" in out
    monkeypatch.setenv("ANDROMEDA_LANGUAGE", "es")
    out_es = with_identity("x", "generalist", "gemma3:27b", user_prompt="sobre minecraft")
    assert "DATOS QUE CAMBIAN" in out_es


# ── Tendencias legibles ────────────────────────────────────────────────────

def test_percentage_metrics_use_percentage_points():
    """Pasar del 8% al 41% de satisfacción no es "+510%": es "+33 puntos".
    El cálculo relativo se dispara con bases pequeñas y resulta absurdo."""
    from app.mlops.quality_history import QualityHistory
    pts = [{"satisfaction": 8}, {"satisfaction": 8},
           {"satisfaction": 41}, {"satisfaction": 41}]
    t = QualityHistory._trend(pts)["satisfaction"]
    assert t["change_pct"] == 33.0
    assert t["unit"] == "pp"


def test_latency_still_uses_relative_change():
    """La latencia no es un porcentaje: ahí el cambio relativo sí tiene sentido."""
    from app.mlops.quality_history import QualityHistory
    pts = [{"p95": 1000}, {"p95": 1000}, {"p95": 2000}, {"p95": 2000}]
    t = QualityHistory._trend(pts)["p95"]
    assert t["change_pct"] == 100.0
    assert t["unit"] == "%"


def test_ui_renders_the_unit():
    src = (ROOT / "frontend/src/components/AnalyticsPanel.jsx").read_text(encoding="utf-8")
    assert "props.tr.unit" in src, "la interfaz no distingue puntos de porcentaje"


# ── Textos en el idioma correcto ───────────────────────────────────────────

def test_no_spanish_leaks_in_the_interface():
    """Con la interfaz en inglés se veían "descargar", "copiar" y "exportar"."""
    fugas = []
    for p in (ROOT / "frontend/src/components").glob("*.jsx"):
        s = p.read_text(encoding="utf-8")
        for palabra in ("descargar", "copiar", "copiado", "exportar"):
            for m in re.finditer(rf">\s*{palabra}\s*<|'{palabra}'|\"{palabra}\"", s):
                linea = s[:m.start()].count("\n") + 1
                contexto = s.split("\n")[linea - 1]
                if "t(" in contexto or "//" in contexto or "*" in contexto:
                    continue
                fugas.append(f"{p.name}:{linea} {palabra}")
    assert not fugas, f"textos sin traducir: {fugas}"


def test_download_labels_are_translated():
    i18n = (ROOT / "frontend/src/stores/i18n.js").read_text(encoding="utf-8")
    for k in ("mb.download", "mb.copy", "mb.copied", "mb.export"):
        assert f"'{k}'" in i18n, f"falta {k}"
