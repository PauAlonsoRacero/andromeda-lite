"""Protección de datos sensibles y robustez de escritura en disco."""
import logging
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parent.parent


def test_gitignore_protects_secrets_anywhere():
    """El directorio de datos es configurable: no basta con ignorar data/.

    Si alguien apunta ANDROMEDA_DATA_DIR dentro del repo, sus claves de API
    acabarían en Git. Los patrones deben ignorar por NOMBRE, no por ruta.
    """
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("mcp_secrets.json", "*.db"):
        assert pattern in gi, f"falta '{pattern}' en .gitignore"


def test_no_user_data_committed():
    """El árbol no debe contener bases de datos ni secretos."""
    offenders = []
    for pattern in ("*.db", "mcp_secrets.json", ".env"):
        for f in ROOT.rglob(pattern):
            if "node_modules" in str(f) or ".git/" in str(f):
                continue
            offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, f"datos de usuario en el árbol: {offenders}"


def test_markdown_render_is_sanitized():
    """XSS real: marked deja pasar el HTML y se inserta con innerHTML.

    Basta pedir que resuma una web o un documento con HTML malicioso para
    llegar ahí; no hace falta un modelo comprometido.
    """
    src = (ROOT / "frontend/src/components/MessageBubble.jsx").read_text(encoding="utf-8")
    assert "DOMPurify" in src, "el markdown se inserta sin sanear"
    assert "ALLOWED_URI_REGEXP" in src, "no se bloquean esquemas javascript:"
    # el saneado debe envolver a marked, no ir por separado
    assert "DOMPurify.sanitize(marked.parse" in src


def test_code_highlight_fallback_escapes():
    """Si el resaltado falla, el código se inserta con innerHTML igualmente."""
    src = (ROOT / "frontend/src/components/Codex.jsx").read_text(encoding="utf-8")
    assert "&amp;" in src and "&lt;" in src, "el fallback no escapa el HTML"


def test_dompurify_is_a_declared_dependency():
    import json
    pkg = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "dompurify" in deps
