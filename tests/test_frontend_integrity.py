"""Integridad del frontend: lo que compila pero rompe al usarse.

Vite genera el paquete aunque falte un import o una traducción. Así llegaron a
Pau "Can't find variable: PromptCatalog" y el menú "settings.prompts".
"""
import glob
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "frontend"
I18N = (FRONT / "src/stores/i18n.js").read_text(encoding="utf-8")
LANGS = ("es", "en", "de", "zh", "fr")


def _claves(lang):
    i = I18N.index(f"  {lang}: {{")
    j = I18N.index("\n  },", i)
    return re.findall(r"^\s*'([^']+)':", I18N[i:j], re.M)


def test_eslint_finds_no_undefined_names():
    """Variables y componentes sin importar (el fallo de PromptCatalog)."""
    eslint = FRONT / "node_modules/.bin/eslint"
    if not eslint.exists() or not shutil.which("node"):
        return   # sin dependencias del frontend en este entorno; la CI lo cubre
    r = subprocess.run([str(eslint), "src"], cwd=FRONT, capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout[-3000:]


def test_no_duplicate_translation_keys():
    """Una clave repetida hace que la segunda pise a la primera sin avisar."""
    for lang in LANGS:
        claves = _claves(lang)
        dup = {k for k in claves if claves.count(k) > 1}
        assert not dup, f"{lang}: {sorted(dup)}"


def test_every_literal_key_is_translated():
    usadas = set()
    for f in glob.glob(str(FRONT / "src/**/*.js*"), recursive=True):
        if f.endswith("i18n.js"):
            continue
        usadas |= set(re.findall(r"\bt\(\s*'([a-zA-Z0-9_.]+)'\s*\)", Path(f).read_text(encoding="utf-8")))
    for lang in LANGS:
        faltan = usadas - set(_claves(lang))
        assert not faltan, f"{lang}: {sorted(faltan)[:20]}"


def test_dynamic_keys_are_translated():
    """Claves construidas al vuelo, como t('settings.' + id)."""
    sp = (FRONT / "src/components/SettingsPanel.jsx").read_text(encoding="utf-8")
    bloque = sp[sp.index("const SECTIONS"):sp.index("]", sp.index("const SECTIONS"))]
    esperadas = [f"settings.{i}" for i in re.findall(r"\{ id: '([a-z_]+)',", bloque)]
    esperadas += [f"phase.{p}" for p in ("thinking", "searching", "writing")]
    esperadas += [f"cs.lvl_{x}" for x in ("low", "mid", "high", "ultra")]
    esperadas += [f"mem.semantic_{x}" for x in ("pending", "waiting_ollama", "downloading",
                                                 "ready", "offline", "error")]
    for lang in LANGS:
        faltan = set(esperadas) - set(_claves(lang))
        assert not faltan, f"{lang}: {sorted(faltan)}"


def test_backend_error_keys_are_translated():
    """El backend envía claves de error que la interfaz traduce."""
    back = set()
    for f in glob.glob(str(ROOT / "backend/app/**/*.py"), recursive=True):
        src = Path(f).read_text(encoding="utf-8")
        back |= set(re.findall(r'"(?:error_key|message_key)"\s*:\s*"([a-z_]+\.[a-z_]+)"', src))
        back |= set(re.findall(r'message_key\s*=\s*"([a-z_]+\.[a-z_]+)"', src))
    for lang in LANGS:
        faltan = back - set(_claves(lang))
        assert not faltan, f"{lang}: {sorted(faltan)}"


# ── Revisión de lo nuevo ───────────────────────────────────────────────────

def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def test_export_copies_to_downloads_without_overwriting(tmp_path, monkeypatch):
    """En escritorio los enlaces de descarga no hacen nada (Word, PDF…)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "informe.docx").write_bytes(b"PK\x03\x04datos")
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(ws))
    with _client(tmp_path, monkeypatch) as c:
        r1 = c.post("/api/files/export", json={"path": "informe.docx"}).json()
        r2 = c.post("/api/files/export", json={"path": "informe.docx"}).json()
        assert r1["name"] == "informe.docx" and r2["name"] == "informe (1).docx"
        assert (tmp_path / "Downloads" / "informe.docx").read_bytes() == b"PK\x03\x04datos"
        assert c.post("/api/files/export", json={"path": "../../etc/passwd"}).status_code in (400, 404)


def test_download_buttons_do_not_use_window_open():
    arte = (FRONT / "src/components/ArtifactsPanel.jsx").read_text(encoding="utf-8")
    assert "downloadWorkspaceFile(file.path)" in arte and "window.open(rawUrl" not in arte


def test_zoom_listener_only_while_open():
    """Cada mensaje registraba un escuchador de teclado permanente."""
    b = (FRONT / "src/components/MessageBubble.jsx").read_text(encoding="utf-8")
    assert "if (!zoom()) return" in b


def test_gdpr_export_does_not_fail_after_saving():
    """Usaba una variable inexistente tras guardar: mostraba error aunque funcionara."""
    p = (FRONT / "src/components/ProfilePanel.jsx").read_text(encoding="utf-8")
    assert "URL.revokeObjectURL(url)" not in p


def test_project_context_reads_each_file_once(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from app.core import projects as pj
    for i in range(5):
        pj.save_file("proj-1234", f"f{i}.md", ("dato " * 2000).encode())
    lecturas = []
    original = pj.read_text
    monkeypatch.setattr(pj, "read_text", lambda *a, **k: lecturas.append(a[1]) or original(*a, **k))
    pj.build_context("proj-1234", "P", "", "dato", max_chars=3000)
    assert len(lecturas) == len(set(lecturas)), "algún archivo se leyó dos veces"
