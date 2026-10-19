"""Diseño 1.0/1.1 con modo claro/oscuro, isla de ventana y memoria por temas."""
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"
CSS = (SRC / "styles/index.css").read_text(encoding="utf-8")


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── Apariencia ─────────────────────────────────────────────────────────────

def test_design_and_mode_are_independent():
    st = (SRC / "stores/settings.js").read_text(encoding="utf-8")
    assert "persisted('andromeda_design', '1.1')" in st
    assert "if (theme() === 'macos') { setDesign('1.1'); setTheme('dark') }" in st, \
        "quien tenía el tema macOS debe pasar a 1.1 oscuro"
    sp = (SRC / "components/SettingsPanel.jsx").read_text(encoding="utf-8")
    assert "S.setDesign('1.0')" in sp and "S.setDesign('1.1')" in sp
    assert "S.setTheme('light')" in sp and "setTheme('macos')" not in sp


def test_design_11_has_light_dark_and_incognito_palettes():
    for sel in ("body.design-11.theme-dark {", "body.design-11.theme-light {", "body.design-11.incognito {"):
        assert sel in CSS, sel


def test_design_11_keeps_colour_spots_but_not_bands():
    assert "body.design-11 .bg-bands { display: none !important; }" in CSS
    assert "body.design-11 .bg-orbs" not in CSS
    st = (SRC / "stores/settings.js").read_text(encoding="utf-8")
    assert "design() === '1.1' && bgStyle() === 'bands'" in st
    sp = (SRC / "components/SettingsPanel.jsx").read_text(encoding="utf-8")
    assert "<Show when={S.design() !== '1.1'}>" in sp


def test_design_11_top_bars_are_seamless():
    i = CSS.index("body.design-11 .titlebar,\nbody.design-11 header {")
    assert "border-bottom: 0 !important" in CSS[i:i + 300]


def test_message_box_has_macos_glass():
    assert "body.design-11 .liquid-glass {" in CSS and "body.design-11 .liquid-glass:focus-within" in CSS


def test_window_buttons_live_in_an_island_above_overlays():
    tb = (SRC / "components/TitleBar.jsx").read_text(encoding="utf-8")
    assert "<Portal>" in tb and 'class="tl-island"' in tb
    i = CSS.index(".tl-island {")
    bloque = CSS[i:i + 400]
    assert "position: fixed" in bloque and "z-index: 10000" in bloque and "border-radius: 999px" in bloque


# ── Memoria por temas ──────────────────────────────────────────────────────

def test_topic_rewrite_by_hand(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        p = c.app.state.memory_profile
        p.upsert_fact("gustos:audi", "Me gusta el Audi TT")
        c.post("/api/memory/profile/file/rewrite",
               json={"section": "temas", "file": "gustos", "text": "- Me gusta el Audi TT mk1\n- Me gusta el fútbol"})
        texto = p.render()
        assert "mk1" in texto and "fútbol" in texto
        archivos = {f["id"] for s in c.get("/api/memory/files").json()["sections"] for f in s["files"]}
        assert "gustos" in archivos


def test_topic_ai_edit_applies_the_described_change(tmp_path, monkeypatch):
    """Como en Claude: se describe el cambio y la IA reescribe el tema."""
    import httpx

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "<think>x</think>- Me gusta el Audi TT mk1\n- Odio el color negro"}}

    enviados = []

    class _Cli:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **k):
            enviados.append(json)
            return _Resp()

    async def resolver(u):
        return "http://ollama"
    import app.ollama_resolver as orv
    monkeypatch.setattr(orv, "resolve_ollama_url", resolver)
    monkeypatch.setattr(httpx, "AsyncClient", _Cli)
    with _client(tmp_path, monkeypatch) as c:
        c.app.state.registry.set_available_models(["qwen3:8b"])
        p = c.app.state.memory_profile
        p.upsert_fact("gustos:audi", "Me gusta el Audi TT")
        p.upsert_fact("gustos:negro", "Me gusta el color negro")
        r = c.post("/api/memory/profile/file/ai-edit", json={
            "section": "temas", "file": "gustos", "name": "Gustos",
            "instruction": "en realidad odio el negro y el audi es un mk1"}).json()
        assert r["lines"] == ["Me gusta el Audi TT mk1", "Odio el color negro"]
        assert "Me gusta el color negro" in enviados[0]["messages"][0]["content"]
        assert "Me gusta el color negro" not in p.render()


def test_people_topics_can_be_rewritten(tmp_path):
    from app.memory.profile import MemoryProfile
    from app.memory.structure import build, replace_file
    p = MemoryProfile(tmp_path / "p.json")
    p.upsert_fact("persona:marc", "mi hermano se llama Marc")
    replace_file(p, "personas", "persona:marc", ["Marc es mi hermano mayor", "Vive en Girona"])
    personas = next(s for s in build(p)["sections"] if s["id"] == "personas")["files"]
    assert len(personas) == 1 and personas[0]["id"] == "persona:marc"
    assert len(personas[0]["facts"]) == 2


def test_memory_ui_matches_claude():
    mf = (SRC / "components/MemoryFiles.jsx").read_text(encoding="utf-8")
    assert "memf-item-actions" in mf and "/api/memory/profile/file/ai-edit" in mf
    assert "memf.describe_change" in mf and "memf-table" not in mf


# ── Pantalla de carga, Windows y publicación ───────────────────────────────

def test_splash_follows_design_and_mode(tmp_path):
    """En un subproceso: desktop.py redirige la salida a su registro y fija
    variables de entorno al importarse, y contaminaría el resto de tests."""
    import os
    import subprocess
    import sys
    codigo = """
import json, sys
sys.path.insert(0, %r)
import desktop as d
d.DATA_DIR.mkdir(parents=True, exist_ok=True)
res = []
for estado in [{}, {"andromeda_design": "1.0"}, {"andromeda_design": "1.1", "andromeda_theme": "light"},
               {"andromeda_theme": "macos"}]:
    (d.DATA_DIR / "ui_state.json").write_text(json.dumps(estado), encoding="utf-8")
    h = d.build_splash_html()
    res.append([('class="card"' in h), ('<body class="light' in h), ("__SPLASH" in h)])
open(%r, "w").write(json.dumps(res))
""" % (str(ROOT), str(tmp_path / "res.json"))
    env = {**os.environ, "HOME": str(tmp_path), "APPDATA": str(tmp_path), "XDG_DATA_HOME": str(tmp_path)}
    subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, timeout=60, cwd=str(tmp_path))
    res = json.loads((tmp_path / "res.json").read_text())
    assert res == [[True, False, False], [False, False, False], [True, True, False], [True, False, False]]


def test_every_text_file_access_declares_utf8():
    """En Windows la codificación por defecto es cp1252: sin encoding, una "ñ"
    o un emoji rompe la lectura o corrompe el archivo."""
    import ast
    import glob
    faltan = []
    for f in glob.glob(str(ROOT / "backend/app/**/*.py"), recursive=True) + [str(ROOT / "desktop.py")]:
        for n in ast.walk(ast.parse(Path(f).read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("read_text", "write_text"):
                if not any(k.arg == "encoding" for k in n.keywords):
                    faltan.append(f"{f}:{n.lineno}")
            if isinstance(n.func, ast.Name) and n.func.id == "open":
                modo = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else "r"
                if "b" not in str(modo) and not any(k.arg == "encoding" for k in n.keywords):
                    faltan.append(f"{f}:{n.lineno}")
    assert not faltan, faltan


def test_onboarding_is_translated():
    chat = (SRC / "components/Chat.jsx").read_text(encoding="utf-8")
    for fijo in ("en el menú lateral", "Vuelve aquí y ya puedes", "El orquestador seleccionará", "llama3.2:3b"):
        assert fijo not in chat, fijo


def test_release_version_has_no_beta_suffix():
    v = (SRC / "version.js").read_text(encoding="utf-8")
    assert "APP_CHANNEL = 'stable'" in v


def test_release_is_ready_to_publish():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    notas = ROOT / "docs" / "releases" / f"v{version}.md"
    assert notas.exists(), "faltan las notas de la release"
    texto = notas.read_text(encoding="utf-8")
    assert "Right-click" in texto and "Run anyway" in texto, "instrucciones para apps sin firmar"
    wf = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "body_path: release-notes.md" in wf and "actions/checkout@v4" in wf
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert cl.count(f"## [{version}]") == 1 and "sin publicar" not in cl.split("\n## ")[1][:40]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "What's new in 1.1" in readme and "160%20passing" not in readme
