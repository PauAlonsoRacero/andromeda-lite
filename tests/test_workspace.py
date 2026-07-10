"""
Tests del workspace de archivos y del parser de acciones de la IA.

Cubre funcionalidad (CRUD, papelera) y SEGURIDAD (path traversal, rutas
absolutas, escapes). La seguridad es crítica porque Andromeda se publica
open source y opera sobre el sistema de archivos local.
"""

import os
import tempfile

import pytest

from app.core.workspace import Workspace, WorkspaceError
from app.core.file_actions import (
    find_actions, execute_actions, strip_action_blocks,
)


@pytest.fixture()
def ws(tmp_path):
    return Workspace(root=tmp_path)


# ── Funcionalidad básica ──────────────────────────────────────────────────────
def test_write_and_read(ws):
    info = ws.write("notas/hola.md", "# Hola\ncontenido")
    assert info.path == "notas/hola.md"
    assert info.size > 0
    assert ws.read("notas/hola.md").startswith("# Hola")


def test_exists(ws):
    ws.write("a.txt", "x")
    assert ws.exists("a.txt") is True
    assert ws.exists("noexiste.txt") is False


def test_mkdir(ws):
    ws.mkdir("proyecto/src")
    assert ws.exists("proyecto/src") is True


def test_move_renames(ws):
    ws.write("viejo.txt", "x")
    ws.move("viejo.txt", "nuevo.txt")
    assert ws.exists("nuevo.txt") is True
    assert ws.exists("viejo.txt") is False


def test_list_returns_entries(ws):
    ws.write("a.txt", "x")
    ws.write("dir/b.txt", "y")
    items = ws.list()
    paths = {i.path for i in items}
    assert "a.txt" in paths
    assert "dir/b.txt" in paths


def test_delete_is_reversible(ws):
    ws.write("borrable.txt", "contenido")
    res = ws.delete("borrable.txt")
    assert res["permanent"] is False
    assert ws.exists("borrable.txt") is False
    # restaurar lo recupera en su ruta original
    ws.restore(res["trash_id"])
    assert ws.exists("borrable.txt") is True


def test_delete_permanent(ws):
    ws.write("adios.txt", "x")
    res = ws.delete("adios.txt", permanent=True)
    assert res["permanent"] is True
    assert ws.exists("adios.txt") is False


def test_restore_preserves_nested_path(ws):
    ws.write("a/b/c/profundo.md", "x")
    res = ws.delete("a/b/c/profundo.md")
    ws.restore(res["trash_id"])
    assert ws.exists("a/b/c/profundo.md") is True


# ── SEGURIDAD: ninguna de estas debe escapar del workspace ────────────────────
@pytest.mark.parametrize("evil", [
    "../../../etc/passwd",
    "/etc/passwd",
    "..\\..\\windows\\system32\\cmd.exe",
    "notas/../../escape.txt",
    "C:\\Windows\\System32",
    "../",
    "..",
])
def test_path_traversal_blocked(ws, evil):
    with pytest.raises(WorkspaceError):
        ws.write(evil, "PWNED")


def test_no_file_written_outside_workspace(ws, tmp_path):
    # Tras intentos de escape, nada debe existir fuera del root
    for evil in ["../../../tmp/andromeda_pwned", "/tmp/andromeda_pwned2"]:
        try:
            ws.write(evil, "x")
        except WorkspaceError:
            pass
    assert not os.path.exists("/tmp/andromeda_pwned")
    assert not os.path.exists("/tmp/andromeda_pwned2")


def test_trash_dir_is_protected(ws):
    # No se puede escribir directamente en la papelera interna
    with pytest.raises(WorkspaceError):
        ws.write(".andromeda_trash/x.txt", "x")


def test_oversized_content_rejected(ws):
    big = "a" * (26 * 1024 * 1024)  # 26 MB > límite de 25 MB
    with pytest.raises(WorkspaceError):
        ws.write("grande.txt", big)


# ── Parser de acciones de la IA ───────────────────────────────────────────────
def test_find_actions_detects_write_and_mkdir():
    text = '''Te creo esto:

```andromeda:write path="x/y.md"
contenido
```

y una carpeta:

```andromeda:mkdir path="z"
```'''
    acts = find_actions(text)
    assert len(acts) == 2
    assert acts[0].action == "write"
    assert acts[0].attrs["path"] == "x/y.md"
    assert acts[1].action == "mkdir"


def test_execute_actions_writes_file(ws):
    text = '```andromeda:write path="salida.md"\nhola desde la IA\n```'
    results = execute_actions(text, ws)
    assert len(results) == 1
    assert results[0].ok is True
    assert ws.read("salida.md").strip() == "hola desde la IA"


def test_execute_actions_delete_is_reversible(ws):
    ws.write("temp.txt", "x")
    text = '```andromeda:delete path="temp.txt"\n```'
    results = execute_actions(text, ws)
    assert results[0].ok is True
    assert ws.exists("temp.txt") is False  # movido a papelera


def test_execute_actions_blocks_traversal(ws):
    text = '```andromeda:write path="../../../etc/pwned"\nx\n```'
    results = execute_actions(text, ws)
    assert results[0].ok is False  # bloqueado, sin excepción


def test_strip_action_blocks_cleans_text():
    text = 'Antes\n```andromeda:write path="a.txt"\nx\n```\nDespués'
    clean = strip_action_blocks(text)
    assert "andromeda:write" not in clean
    assert "Antes" in clean
    assert "Después" in clean


def test_text_without_actions_returns_empty():
    assert find_actions("solo texto normal sin bloques") == []
    assert execute_actions("nada que hacer aquí") == []


# ── Parser tolerante + documentos binarios (bugs reales en producción) ────────

def test_parser_tolerates_model_variants():
    """Los modelos locales generan variantes; el parser debe pillarlas todas."""
    from app.core.file_actions import find_actions, has_actions
    casos = [
        ':write path="numeros.txt"\n1\n2\n3',                 # sin fence, con :
        '```write path="x.txt"\nhola\n```',                   # fence sin andromeda:
        '```andromeda:write path="y.md"\ntexto\n```',         # canónico
        'andromeda:write path="z.txt"\ncontenido',            # sin fence ni :
    ]
    for c in casos:
        assert has_actions(c), f"No detectó: {c[:30]}"
        acts = find_actions(c)
        assert acts[0].action == "write"
        assert acts[0].attrs.get("path")


def test_docx_is_real_word_file(tmp_path, monkeypatch):
    """Crear .docx produce un Word real (ZIP con document.xml), no texto."""
    import zipfile
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    nums = "\n".join(str(i) for i in range(1, 101))
    resp = f':write path="numeros.docx"\n# Numeros\n{nums}'
    results = execute_actions(resp)
    assert results and results[0].ok
    docx = tmp_path / "numeros.docx"
    assert docx.exists()
    assert zipfile.is_zipfile(docx)
    with zipfile.ZipFile(docx) as z:
        assert "word/document.xml" in z.namelist()


def test_xlsx_and_pdf_real(tmp_path, monkeypatch):
    import zipfile
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    # xlsx
    execute_actions(':write path="d.xlsx"\na,b,c\n1,2,3')
    xlsx = tmp_path / "d.xlsx"
    assert xlsx.exists() and zipfile.is_zipfile(xlsx)
    # pdf (empieza por %PDF)
    execute_actions(':write path="r.pdf"\nHola mundo')
    pdf = tmp_path / "r.pdf"
    assert pdf.exists() and pdf.read_bytes()[:4] == b"%PDF"


def test_context_block_includes_existing_files(tmp_path, monkeypatch):
    """El contexto del workspace lista archivos y muestra contenido de texto,
    para que la IA pueda MODIFICAR en vez de duplicar."""
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.workspace import Workspace
    ws = Workspace()
    ws.write("index.html", "<html><body>hola</body></html>")
    ws.write("notas.txt", "comprar pan")
    ctx = ws.context_block()
    assert "index.html" in ctx
    assert "notas.txt" in ctx
    # incluye el contenido para poder editarlo
    assert "hola" in ctx or "comprar pan" in ctx


# ── Todas las acciones de archivo (append, edit, copy, read) ─────────────────

def test_action_append(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    execute_actions(':write path="log.txt"\nlinea1')
    execute_actions(':append path="log.txt"\nlinea2')
    content = (tmp_path / "log.txt").read_text()
    assert "linea1" in content and "linea2" in content


def test_action_edit_inline_and_body(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    # edit en una línea (find/replace en atributos)
    execute_actions(':write path="a.txt"\nhola mundo')
    r = execute_actions(':edit path="a.txt" find="hola" replace="adios"')
    assert r and r[0].ok
    assert (tmp_path / "a.txt").read_text() == "adios mundo"
    # edit con cuerpo (find---replace)
    execute_actions(':write path="b.txt"\nfoo bar baz')
    r = execute_actions(':edit path="b.txt"\nbar\n---\nQUX')
    assert r and r[0].ok
    assert "QUX" in (tmp_path / "b.txt").read_text()


def test_action_edit_missing_text_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    execute_actions(':write path="a.txt"\nhola')
    r = execute_actions(':edit path="a.txt" find="NOEXISTE" replace="x"')
    assert r and not r[0].ok  # error claro, no excepción


def test_action_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    execute_actions(':write path="orig.txt"\ncontenido original')
    r = execute_actions(':copy src="orig.txt" dst="copia.txt"')
    assert r and r[0].ok
    assert (tmp_path / "copia.txt").read_text() == "contenido original"
    assert (tmp_path / "orig.txt").exists()  # el original sigue


def test_action_read(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.core.file_actions import execute_actions
    execute_actions(':write path="datos.txt"\nlinea de datos')
    r = execute_actions(':read path="datos.txt"')
    assert r and r[0].ok
    assert "linea de datos" in r[0].detail


def test_all_actions_detected():
    """find_actions detecta las 8 acciones."""
    from app.core.file_actions import find_actions
    for action in ["write", "append", "edit", "mkdir", "delete", "move", "copy", "read"]:
        if action in ("write", "append"):
            txt = f':{action} path="x.txt"\ncontenido'
        elif action == "edit":
            txt = ':edit path="x.txt" find="a" replace="b"'
        elif action in ("move", "copy"):
            txt = f':{action} src="a.txt" dst="b.txt"'
        else:
            txt = f':{action} path="x"'
        acts = find_actions(txt)
        assert acts and acts[0].action == action, f"falló: {action}"
