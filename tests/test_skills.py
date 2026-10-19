"""Skills: descubrimiento, matching y API."""
import logging

logging.disable(logging.CRITICAL)


def test_loader_discovers_skills_from_disk(tmp_path):
    from app.skills.loader import SkillRegistry
    d = tmp_path / "skills" / "greet"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: Greeter\ndescription: Saludar de forma cálida y breve.\n"
        "specialists: [generalist]\n---\nSaluda con calidez.", encoding="utf-8")
    reg = SkillRegistry(tmp_path / "skills")
    assert reg.reload() == 1
    assert reg.skills["greet"].name == "Greeter"
    assert reg.skills["greet"].specialists == ["generalist"]


def test_loader_ignores_folders_without_skill_md(tmp_path):
    from app.skills.loader import SkillRegistry
    (tmp_path / "skills" / "empty").mkdir(parents=True)
    assert SkillRegistry(tmp_path / "skills").skills == {}


def test_match_selects_right_skill_across_real_catalog():
    """Con el catálogo real de 9 skills, cada prompt activa la correcta."""
    from app.skills.loader import SkillRegistry
    reg = SkillRegistry("config/skills")
    casos = [
        ("por qué mi script lanza un TypeError", "debugging"),
        ("esta consulta SQL va lentísima, tarda 8 segundos", "sql-optimization"),
        ("revisa este pull request antes de mergear", "code-review"),
        ("escribe el README de instalación del proyecto", "technical-writing"),
        ("el servidor devuelve 500 en producción ahora mismo", "incident-response"),
        ("diseña los endpoints REST del recurso pedidos", "api-design"),
        ("limpia este código y quita la duplicación", "refactoring"),
    ]
    for prompt, esperado in casos:
        hits = reg.match(prompt, k=1)
        assert hits and hits[0].id == esperado, f"{prompt!r} activó {hits and hits[0].id}"


def test_match_does_not_fire_on_unrelated_or_short_prompts():
    """Lo importante: no inyectar instrucciones cuando no toca."""
    from app.skills.loader import SkillRegistry
    reg = SkillRegistry("config/skills")
    for prompt in ["hola qué tal", "gracias", "sí",
                   "cuál es la capital de Francia", "escríbeme un poema sobre el mar"]:
        assert reg.match(prompt, k=1) == [], f"{prompt!r} no debería activar nada"


def test_match_empty_registry_is_safe(tmp_path):
    from app.skills.loader import SkillRegistry
    assert SkillRegistry(tmp_path / "skills").match("cualquier cosa") == []


def test_skills_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        ids = [s["id"] for s in c.get("/api/skills").json()["skills"]]
        assert len(ids) >= 9 and "code-review" in ids
        assert "body" in c.get("/api/skills/code-review").json()
        assert c.get("/api/skills/no-existe").status_code == 404
        r = c.get("/api/skills/match", params={"q": "revisa este pull request"})
        assert any(m["id"] == "code-review" for m in r.json()["matched"])
        assert c.post("/api/skills/reload").json()["count"] >= 9
