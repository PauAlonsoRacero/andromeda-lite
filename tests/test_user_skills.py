"""Skills creadas por el usuario (equivalente a los Gems)."""
import logging

logging.disable(logging.CRITICAL)


def test_create_and_match_user_skill(tmp_path):
    from app.skills.loader import SkillRegistry
    reg = SkillRegistry(tmp_path / "factory", user_skills_dir=tmp_path / "user")
    sk = reg.save_user_skill(
        "mi-estilo", "Mi estilo", "Escribir correos de trabajo en mi tono habitual.",
        "Sé breve y directo. Nunca uses signos de exclamación.", triggers="correo email redactar")
    assert sk.user_created is True
    hits = reg.match("redacta un correo para el cliente", k=1)
    assert hits and hits[0].id == "mi-estilo"


def test_user_skill_overrides_factory_skill(tmp_path):
    """Si el usuario crea una skill con el id de una de fábrica, gana la suya."""
    from app.skills.loader import SkillRegistry
    fac = tmp_path / "factory" / "code-review"
    fac.mkdir(parents=True)
    (fac / "SKILL.md").write_text(
        "---\nname: De fábrica\ndescription: Revisar código.\n---\nOriginal.", encoding="utf-8")
    reg = SkillRegistry(tmp_path / "factory", user_skills_dir=tmp_path / "user")
    assert reg.skills["code-review"].name == "De fábrica"
    reg.save_user_skill("code-review", "Mi revisión", "Revisar código a mi manera.", "Mío.")
    assert reg.skills["code-review"].name == "Mi revisión"
    assert reg.skills["code-review"].user_created is True


def test_description_is_required(tmp_path):
    import pytest
    from app.skills.loader import SkillRegistry
    reg = SkillRegistry(tmp_path / "factory", user_skills_dir=tmp_path / "user")
    with pytest.raises(ValueError):
        reg.save_user_skill("x", "X", "   ", "cuerpo")


def test_delete_user_skill(tmp_path):
    from app.skills.loader import SkillRegistry
    reg = SkillRegistry(tmp_path / "factory", user_skills_dir=tmp_path / "user")
    reg.save_user_skill("temp", "Temp", "Una skill temporal de prueba.", "cuerpo")
    assert reg.delete_user_skill("temp") is True
    assert "temp" not in reg.skills
    assert reg.delete_user_skill("no-existe") is False


def test_user_skills_api(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.post("/api/skills/user", json={
            "id": "resumenes", "name": "Resúmenes cortos",
            "description": "Resumir textos largos en tres puntos clave.",
            "triggers": "resume resumen puntos clave",
            "body": "Devuelve exactamente tres viñetas, sin introducción."})
        assert r.status_code == 200 and r.json()["saved"]
        skills = c.get("/api/skills").json()["skills"]
        mine = [s for s in skills if s["id"] == "resumenes"]
        assert mine and mine[0]["user_created"] is True
        # las de fábrica están protegidas
        assert c.delete("/api/skills/user/code-review").status_code == 403
        assert c.delete("/api/skills/user/resumenes").json()["deleted"] is True


def test_api_rejects_empty_description(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        assert c.post("/api/skills/user", json={"id": "x", "name": "X",
                                                "description": ""}).status_code == 400
