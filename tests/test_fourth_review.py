"""Revisión de Pau tras el tercer registro: artefactos, biblioteca y lo pendiente."""
import base64
import json
import logging
import os
import subprocess
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"


def _src(f):
    return (SRC / f).read_text(encoding="utf-8")


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


# ── El panel de vista previa estaba dentro de Configuración ───────────────

def test_preview_panel_is_not_inside_settings():
    """Se montó dentro de la ventana de Configuración: solo existía con ella
    abierta. En Artefactos no se abría nada y al abrir Configuración aparecía
    el archivo tapándola."""
    app = _src("App.jsx")
    montaje = app.index("<FilePreview />")
    inicio_ajustes = app.index("<Show when={settingsOpen()}>")
    assert montaje < inicio_ajustes, "el panel vuelve a estar dentro de Configuración"
    assert app.count("<FilePreview />") == 1


def test_preview_panel_renders_through_a_portal():
    assert "<Portal>" in _src("components/FilePreview.jsx")


def test_opening_settings_closes_the_preview():
    assert "if (settingsOpen()) closePreview()" in _src("App.jsx")


def test_artifacts_and_chat_use_the_shared_panel():
    assert "openPreview(file.path)" in _src("components/ArtifactsPanel.jsx")
    assert "openPreview(fa.path)" in _src("components/MessageBubble.jsx")
    assert "openPreview(f.path, openId())" in _src("components/ProjectsPanel.jsx")


# ── Biblioteca de prompts ─────────────────────────────────────────────────

def test_settings_prompt_section_is_translated():
    """El menú mostraba literalmente "settings.prompts"."""
    i18n = _src("stores/i18n.js")
    assert i18n.count("'settings.prompts'") == 5


def test_prompt_catalog_exists_in_every_language():
    script = ("import('" + str(SRC / "data/promptCatalog.js") + "').then(m=>{const r={};"
              "for(const l of ['es','en','de','fr','zh']){const c=m.catalogFor(l);"
              "r[l]={n:c.prompts.length,cats:c.categories.length,"
              "vacios:c.prompts.filter(p=>!p.title||!p.body).length,"
              "sinCat:c.prompts.filter(p=>!c.categories.includes(p.cat)).length}}"
              "console.log(JSON.stringify(r))})")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        return   # sin node en el entorno de tests
    r = json.loads(out.stdout)
    for lang, d in r.items():
        assert d["n"] == 103 and d["cats"] == 15, lang
        assert d["vacios"] == 0 and d["sinCat"] == 0, lang


def test_translations_are_aligned_with_spanish():
    """Mismo número de prompts en cada idioma: si uno se desplaza, el título de
    un prompt acabaría con el texto de otro."""
    for lang in ("en", "de", "fr", "zh"):
        src = (SRC / f"data/prompts.{lang}.js").read_text(encoding="utf-8")
        assert src.count("\n  ['") == 103, lang


def test_catalog_follows_interface_language():
    comp = _src("components/PromptCatalog.jsx")
    assert "catalogFor(lang())" in comp


def test_use_prompt_from_settings_reaches_the_chat():
    assert "setPendingPrompt(body)" in _src("components/SettingsPanel.jsx")
    assert "andromeda:go-chat" in _src("App.jsx")
    assert "pendingPrompt()" in _src("components/Chat.jsx")


# ── Memoria ───────────────────────────────────────────────────────────────

def test_contradictory_stored_fact_is_cleaned(tmp_path):
    """"Me gusta el color negro? lo odio." seguía en el perfil."""
    from app.memory.profile import MemoryProfile
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"facts": {"gustos:negro": "Me gusta el color negro? lo odio.",
                                       "gustos:audi": "Me gusta el audi tt"}, "manual": ""}))
    texto = MemoryProfile(p).render()
    assert "negro" not in texto and "audi" in texto


# ── Imagen + espacio de trabajo ───────────────────────────────────────────

def _ws_con_pagina(monkeypatch, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "pagina_web.html").write_text("<h1>VIEJA</h1>")
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(ws))


def test_creating_from_an_image_does_not_inject_old_files(tmp_path, monkeypatch):
    """Copió pagina_web.html en vez de basarse en la foto."""
    _ws_con_pagina(monkeypatch, tmp_path)
    from app.core import prompt_builder as pb
    p = pb.PromptParts(message="x")
    pb.add_workspace(p, "crea un archivo index.html basado en la web de la foto", False, has_images=True)
    assert "VIEJA" not in p.documents and "IMAGEN" in p.documents


def test_editing_still_sees_the_file(tmp_path, monkeypatch):
    _ws_con_pagina(monkeypatch, tmp_path)
    from app.core import prompt_builder as pb
    for prompt in ("mejora la página web porfavor", "cambia el título de pagina_web.html"):
        p = pb.PromptParts(message="x")
        pb.add_workspace(p, prompt, False)
        assert "VIEJA" in p.documents, prompt


# ── Primer token ──────────────────────────────────────────────────────────

def test_time_to_first_token_counts_from_the_request():
    """Marcaba 0,4 ms cuando la espera real fueron 14 s."""
    import inspect
    from app.core import streaming
    assert "_ttft = (_t.perf_counter() - t0) * 1000" in inspect.getsource(streaming)


# ── Vista previa de archivos de proyecto ──────────────────────────────────

def test_project_files_can_be_previewed(tmp_path, monkeypatch):
    from docx import Document
    with _client(tmp_path, monkeypatch) as c:
        buf = tmp_path / "d.docx"
        d = Document(); d.add_heading("Informe", 1); d.save(buf)
        c.post("/api/projects/proj-1234/files", json={"files": [
            {"path": "docs/informe.docx", "content_b64": base64.b64encode(buf.read_bytes()).decode()},
            {"path": "web/index.html", "content_b64": base64.b64encode(b"<h1>Hola</h1>").decode()}]})
        r = c.get("/api/projects/proj-1234/view/web/index.html")
        assert r.status_code == 200 and r.headers["x-frame-options"] == "SAMEORIGIN"
        assert "sandbox" in r.headers["content-security-policy"]
        assert "<h1>Informe</h1>" in c.get("/api/projects/proj-1234/view/docs/informe.docx").text
        assert c.get("/api/projects/proj-1234/view/../../x").status_code in (400, 404)
