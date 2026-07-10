"""Tests del Model Registry: registro, promoción y servir producción."""
import sys, tempfile
sys.path.insert(0, "backend")
from app.mlops.registry import ModelRegistry


def test_register_starts_in_staging_with_autoversion():
    reg = ModelRegistry(tempfile.mktemp(suffix=".json"))
    e1 = reg.register("mistral:7b", eval_score=4.2)
    e2 = reg.register("mistral:7b", eval_score=4.5)
    assert e1["stage"] == "staging"
    assert e1["version"] == "v1" and e2["version"] == "v2"
    assert e1["eval_score"] == 4.2


def test_promote_to_production_is_exclusive():
    reg = ModelRegistry(tempfile.mktemp(suffix=".json"))
    a = reg.register("mistral:7b")
    b = reg.register("llama3:8b")
    reg.promote(a["id"], "production")
    assert reg.production_model() == "mistral:7b"
    # Promover B a producción debe archivar A automáticamente.
    reg.promote(b["id"], "production")
    assert reg.production_model() == "llama3:8b"
    assert reg.get(a["id"])["stage"] == "archived"
    assert reg.get(b["id"])["promoted_at"] is not None


def test_promote_invalid_stage_raises():
    reg = ModelRegistry(tempfile.mktemp(suffix=".json"))
    a = reg.register("m")
    try:
        reg.promote(a["id"], "banana")
        assert False, "debería lanzar ValueError"
    except ValueError:
        pass


def test_delete_and_no_production():
    reg = ModelRegistry(tempfile.mktemp(suffix=".json"))
    a = reg.register("m")
    assert reg.production_model() is None    # nada en producción aún
    assert reg.delete(a["id"]) is True
    assert reg.get(a["id"]) is None
