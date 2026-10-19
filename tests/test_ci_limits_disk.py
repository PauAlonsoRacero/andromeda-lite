"""Límites de entrada, robustez de disco y cobertura del CI."""
import logging
import os
import stat
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


# ── Límites de entrada ─────────────────────────────────────────────────────

def test_prompt_has_a_maximum_length():
    """Sin tope, un pegado accidental de 50 MB cuelga la aplicación."""
    from app.models.schemas import ChatRequest
    campo = ChatRequest.model_fields["prompt"]
    limites = [m for m in campo.metadata if hasattr(m, "max_length")]
    assert limites, "el prompt no tiene límite máximo"


def test_oversized_prompt_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.post("/api/chat", json={"prompt": "x" * 150_000, "stream": False})
        assert r.status_code == 422
        # y un prompt normal sigue funcionando
        assert c.post("/api/chat",
                      json={"prompt": "hola", "stream": False}).status_code == 200


# ── Robustez de disco ──────────────────────────────────────────────────────

def _readonly_dir():
    d = tempfile.mkdtemp()
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    return d


def test_rag_survives_unwritable_disk():
    """Perder la persistencia es molesto; perder la petición del usuario, peor."""
    from app.rag.bm25 import BM25Index
    d = _readonly_dir()
    try:
        idx = BM25Index(os.path.join(d, "sub", "rag.json"))
        idx.add_document("x", "contenido de prueba indexable")
        assert idx.query("contenido prueba"), "el índice quedó inutilizable"
    finally:
        os.chmod(d, stat.S_IRWXU)


def test_memory_profile_survives_unwritable_disk():
    from app.memory.profile import MemoryProfile
    d = _readonly_dir()
    try:
        p = MemoryProfile(os.path.join(d, "sub", "perfil.json"))
        p.set_manual("dato de prueba")          # no debe lanzar
    finally:
        os.chmod(d, stat.S_IRWXU)


# ── Cobertura del CI ───────────────────────────────────────────────────────

def _ci():
    import yaml
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def test_ci_tests_on_all_three_platforms():
    """El producto es una app de escritorio para macOS y Windows, pero el CI
    solo probaba en Linux. Todos los fallos de empaquetado aparecieron en la
    máquina del usuario porque en Linux ni siquiera existen."""
    sistemas = _ci()["jobs"]["test-backend"]["strategy"]["matrix"]["os"]
    for s in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert s in sistemas, f"el CI no prueba en {s}"


def test_ci_verifies_the_desktop_build():
    jobs = _ci()["jobs"]
    assert "build-desktop" in jobs, "el CI no verifica el empaquetado"
    sistemas = jobs["build-desktop"]["strategy"]["matrix"]["os"]
    assert "macos-latest" in sistemas and "windows-latest" in sistemas


def test_ci_checks_pyobjc_on_macos():
    """Sin pyobjc la app se genera pero no abre, y falla en silencio."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pyobjc" in ci
    assert "import objc" in ci


def test_ci_fails_when_desktop_build_fails():
    """El empaquetado es el producto principal: no puede quedar en informativo."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "needs.build-desktop.result" in ci
