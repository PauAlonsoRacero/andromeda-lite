"""Intérpretes de Codex, skills empaquetadas, potencia, caché de prompt y MCP."""
import os
import stat
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"
CSS = (SRC / "styles/index.css").read_text(encoding="utf-8")


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Codex: intérpretes ────────────────────────────────────────────────────

def test_python_code_actually_runs(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/sandbox/run", json={"language": "python", "code": "print(6*7)"}).json()
        assert r.get("stdout", "").strip() == "42", r


def test_installed_interpreter_is_found_verified_and_runnable(tmp_path, monkeypatch):
    """Antes: 'instalado' pero el comando quedaba vacío y no ejecutaba nada."""
    if sys.platform.startswith("win"):
        return
    import asyncio
    import app.routes.sandbox as sb
    carpeta = tmp_path / "bin"
    carpeta.mkdir()
    lua = carpeta / "lua"
    lua.write_text('#!/bin/sh\nif [ "$1" = "-v" ]; then echo Lua 5.4; exit 0; fi\necho corrio\n', encoding="utf-8")
    lua.chmod(lua.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(sb, "_extra_dirs", lambda: [str(carpeta)])
    monkeypatch.setattr(sb, "_detect_pkg_manager", lambda: "apt")

    class _P:
        returncode = 0

        async def communicate(self):
            return (b"ok", None)

    async def _exec(*a, **k):
        return _P()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/sandbox/install", json={"language": "lua"}).json()
        assert r["success"] and r["available_now"] and r["path"] == str(lua)
        out = c.post("/api/sandbox/run", json={"language": "lua", "code": "print(1)"}).json()
        assert out.get("stdout", "").strip() == "corrio"


def test_store_python_alias_is_ignored(monkeypatch):
    import shutil
    import app.routes.sandbox as sb
    monkeypatch.setattr(shutil, "which", lambda c: r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe")
    assert sb._which("python") is None


def test_deno_runs_with_run_subcommand():
    import app.routes.sandbox as sb
    assert sb._ARGS["deno"][0] == "run" and sb._ARGS["go"] == ["run", "{file}"]


def test_negative_detection_is_retried():
    """Un 'no disponible' no puede quedarse guardado hasta reiniciar."""
    import inspect
    import app.routes.sandbox as sb
    assert 'ahora - cfg["checked"] < 10' in inspect.getsource(sb._detect_languages)


# ── Skills en la app empaquetada ──────────────────────────────────────────

def test_skills_are_found_in_packaged_layout(tmp_path):
    import shutil
    import types
    import app as A
    destino = tmp_path / "Frameworks" / "config"
    shutil.copytree(ROOT / "config", destino)
    s = types.SimpleNamespace(specialists_config_path=str(destino / "specialists.yaml"))
    d = A._find_skills_dir(s)
    from app.skills.loader import SkillRegistry
    assert d == destino / "skills" and len(SkillRegistry(d).skills) >= 9


# ── Potencia de IA ────────────────────────────────────────────────────────

def test_power_scales_with_the_prompt():
    from app.core.linear_orchestrator import decide_power
    todos = {"low", "mid", "high", "ultra"}
    assert decide_power("hola", available_levels=todos).level == "low"
    assert decide_power("vale pero dame el link al menos", available_levels=todos).level == "low"
    assert decide_power("Demuestra que la raíz de 2 es irracional", available_levels=todos).level in ("high", "ultra")


def test_power_decision_is_visible_in_diagnostics():
    src = (ROOT / "backend/app/routes/chat.py").read_text(encoding="utf-8")
    assert '_dg.log("power"' in src and "modelo forzado por el usuario" in src


def test_readme_explains_ai_power():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## ⚡ AI power" in readme and "Forcing a model turns automatic power off" in readme


# ── Caché de prefijo: la hora al final ────────────────────────────────────

def test_system_prompt_prefix_is_stable_across_minutes(monkeypatch):
    from datetime import datetime
    from unittest import mock
    import app.specialists.identity as idn

    class _F(datetime):
        t = datetime(2026, 9, 26, 10, 0)

        @classmethod
        def now(cls, tz=None):
            return cls.t
    with mock.patch("datetime.datetime", _F):
        a = idn.with_identity("x", "generalist", "qwen3:8b", user_prompt="hola")
        _F.t = datetime(2026, 9, 26, 10, 37)
        b = idn.with_identity("x", "generalist", "qwen3:8b", user_prompt="hola")
    comun = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), len(a))
    assert comun / len(a) > 0.95, "la hora al principio invalida la caché de Ollama"
    assert a.lstrip().startswith(("FECHA ACTUAL", "CURRENT DATE")), "la fecha debe seguir primero"


# ── Analíticas, apariencia y MCP ──────────────────────────────────────────

def test_component_metrics_are_translatable():
    src = (ROOT / "backend/app/routes/components_health.py").read_text(encoding="utf-8")
    assert src.count('"metric_key"') >= 14
    assert "c.metric_key ? t(c.metric_key)" in (SRC / "components/ComponentsHealth.jsx").read_text(encoding="utf-8")


def test_component_cards_animate_and_glow_stays_inside():
    ch = (SRC / "components/ComponentsHealth.jsx").read_text(encoding="utf-8")
    assert "el.animate(" in ch
    assert ".ch-card-glow { display: none; }" in CSS


def test_accent_colours_include_the_andromeda_gradient():
    st = (SRC / "stores/settings.js").read_text(encoding="utf-8")
    assert "id: 'andromeda'" in st and "linear-gradient" in st
    assert "var(--accent-fill" in CSS


def test_background_palette_is_reachable_in_design_11():
    sp = (SRC / "components/SettingsPanel.jsx").read_text(encoding="utf-8")
    assert "S.bgStyle()===" not in sp


def test_fonts_are_bundled_not_loaded_from_google():
    for f in ("index.html", "src/styles/index.css", "src/index.jsx"):
        assert "fonts.googleapis" not in (ROOT / "frontend" / f).read_text(encoding="utf-8"), f


def test_power_panel_has_open_and_close_animation():
    chat = (SRC / "components/Chat.jsx").read_text(encoding="utf-8")
    assert "classList={{ closing: cfgClosing() }}" in chat
    assert ".ias-expand.closing" in CSS and "body.design-11 .ias-seg-btn.on" in CSS


def test_new_mcp_connectors():
    d = yaml.safe_load((ROOT / "config/mcp_servers.yaml").read_text(encoding="utf-8"))["servers"]
    assert d["gmail"]["command"][-1] == "@artymclabin/gmail-mcp"
    assert d["google-calendar"]["requires_key"] == ["GOOGLE_OAUTH_CREDENTIALS"]
    assert "whatsapp" not in d, "retirado: no oficial y con riesgo de bloqueo del número"
