"""El catálogo de conectores MCP debe estar bien formado."""
import yaml


def test_mcp_catalog_is_well_formed():
    cfg = yaml.safe_load(open("config/mcp_servers.yaml", encoding="utf-8"))
    servers = cfg["servers"]
    assert len(servers) >= 8
    for sid, s in servers.items():
        assert s.get("label"), f"{sid} sin label"
        assert s.get("description"), f"{sid} sin descripción"
        assert isinstance(s.get("command"), list) and s["command"], f"{sid} sin comando"
        assert s.get("runtime") in ("node", "python"), f"{sid} runtime inválido"
        assert s.get("enabled") is False, f"{sid} debe venir desactivado por defecto"
        assert isinstance(s.get("requires_key", []), list)
        # toda variable requerida debe estar declarada en env
        for key in s.get("requires_key", []):
            assert key in (s.get("env") or {}), f"{sid}: {key} requerido pero no está en env"


def test_mcp_catalog_has_keyless_options():
    """Debe haber conectores usables sin configurar ninguna API key."""
    cfg = yaml.safe_load(open("config/mcp_servers.yaml", encoding="utf-8"))
    keyless = [s for s in cfg["servers"].values() if not s.get("requires_key")]
    assert len(keyless) >= 5
