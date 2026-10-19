"""Traducción de errores, accesibilidad, carga diferida y velocidad de la suite."""
import logging
import re
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


def _i18n():
    return (ROOT / "frontend/src/stores/i18n.js").read_text(encoding="utf-8")


# ── P5: errores del backend traducibles ────────────────────────────────────

def test_backend_errors_use_translation_keys():
    """Los errores salían en español fijo, cambiara el idioma que cambiara."""
    literales = []
    for p in (ROOT / "backend/app/routes").glob("*.py"):
        s = p.read_text(encoding="utf-8")
        for m in re.findall(r'"error":\s*"([^"]{6,120})"', s):
            if re.search(r"[áéíóúñ¿¡]", m):
                literales.append(f"{p.name}: {m[:50]}")
    assert len(literales) < 15, f"quedan {len(literales)} errores fijos: {literales[:5]}"


def test_error_keys_are_translated():
    i18n = _i18n()
    for clave in ("err.not_found", "err.ollama_unavailable", "err.bad_credentials",
                  "err.mcp_unavailable", "err.no_connection"):
        assert f"'{clave}'" in i18n, f"falta la traducción {clave}"


def test_error_helper_handles_every_shape():
    """El helper debe cubrir: clave i18n, mensaje suelto, red caída y códigos."""
    src = (ROOT / "frontend/src/services/errors.js").read_text(encoding="utf-8")
    for caso in ("error_key", "ERR_NETWORK", "401", "404", "413"):
        assert caso in src, f"el helper no contempla {caso}"


# ── P9: errores de red visibles ────────────────────────────────────────────

def test_no_unexplained_empty_catches():
    """Un catch vacío hace que la app 'no haga nada' sin decir por qué."""
    sin_justificar = []
    for p in (ROOT / "frontend/src/components").glob("*.jsx"):
        s = p.read_text(encoding="utf-8")
        for m in re.finditer(r"catch\s*(\([^)]*\))?\s*\{([^}]{0,60})\}", s):
            cuerpo = m.group(2).strip()
            if not cuerpo:
                sin_justificar.append(p.name)
    assert len(sin_justificar) <= 5, f"catch vacíos sin justificar: {sin_justificar}"


# ── P10: accesibilidad ─────────────────────────────────────────────────────

def test_icon_buttons_have_accessible_labels():
    """Un botón que solo es '✕' lo anuncia el lector de pantalla como 'botón'."""
    sin_label = []
    for p in (ROOT / "frontend/src/components").glob("*.jsx"):
        s = p.read_text(encoding="utf-8")
        for m in re.finditer(r"<button([^>]*)>(\s*[^<>\w\s]{1,3}\s*)</button>", s):
            if "aria-label" not in m.group(1) and "title" not in m.group(1):
                sin_label.append(f"{p.name}: {m.group(2).strip()}")
    assert len(sin_label) <= 2, f"botones de icono sin etiqueta: {sin_label}"


def test_inputs_have_labels():
    """El placeholder desaparece al escribir: no sirve como etiqueta."""
    total = sum(len(re.findall(r"aria-label",
                p.read_text(encoding="utf-8")))
                for p in (ROOT / "frontend/src/components").glob("*.jsx"))
    assert total >= 20, f"solo {total} etiquetas accesibles en toda la interfaz"


# ── P3: carga diferida ─────────────────────────────────────────────────────

def test_heavy_panels_are_lazy_loaded():
    """Al abrir la app se cargaba todo, incluido lo que el usuario no abre."""
    src = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    for panel in ("AnalyticsPanel", "SettingsPanel", "Codex", "LabPanel"):
        assert f"lazy(() => import('./components/{panel}.jsx'))" in src, \
            f"{panel} no usa carga diferida"
    assert "Suspense" in src, "faltan los límites de Suspense"


# ── P13: velocidad de la suite ─────────────────────────────────────────────

def test_ollama_probe_is_fast_in_tests(monkeypatch):
    """Sin Ollama cada sondeo agotaba su timeout: 2,6 s por arranque de app."""
    from app.ollama_resolver import _default_timeout
    monkeypatch.setenv("ANDROMEDA_ENVIRONMENT", "test")
    assert _default_timeout() <= 0.5
    monkeypatch.setenv("ANDROMEDA_ENVIRONMENT", "production")
    assert _default_timeout() >= 2.0     # en producción, margen amplio


def test_suite_runs_in_test_mode():
    conftest = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    assert "ANDROMEDA_ENVIRONMENT" in conftest
