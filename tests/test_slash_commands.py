"""Slash commands: parseo, expansión y listado."""
import pytest


def test_expand_prompt_command():
    from app.core.slash_commands import expand
    out = expand("/explain qué es un mutex")
    assert "qué es un mutex" in out
    assert len(out) > 40                       # se expandió a una instrucción completa


def test_alias_works_in_spanish():
    from app.core.slash_commands import expand
    assert "recursividad" in expand("/explica recursividad")


def test_non_command_text_untouched():
    from app.core.slash_commands import expand
    txt = "esto no es un comando"
    assert expand(txt) == txt
    assert expand("/noexiste algo") == "/noexiste algo"


def test_command_without_args_untouched():
    """Sin argumentos no se expande: el usuario aún está escribiendo."""
    from app.core.slash_commands import expand
    assert expand("/explain") == "/explain"


def test_action_commands_not_expanded():
    from app.core.slash_commands import expand, parse
    cmd, _ = parse("/clear")
    assert cmd.kind == "action"
    assert expand("/clear") == "/clear"        # las acciones no van al modelo


def test_list_commands_has_no_duplicate_aliases():
    from app.core.slash_commands import list_commands
    names = [c["name"] for c in list_commands()]
    assert len(names) == len(set(names))       # alias no aparecen como entradas sueltas
    assert "explain" in names and "explica" not in names


def test_commands_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.get("/api/commands")
        assert r.status_code == 200
        assert len(r.json()["commands"]) >= 10
