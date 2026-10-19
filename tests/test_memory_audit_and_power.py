"""Revisión de memoria (el "color negro"), potencia por razonamiento, pack,
zoom, MCP depurado y animaciones."""
import asyncio
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"
CSS = (SRC / "styles/index.css").read_text(encoding="utf-8")


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


class _Store:
    def __init__(self, recs):
        self.recs = [{"id": str(i), "content": c} for i, c in enumerate(recs)]
        self.busquedas = 0

    async def search(self, q, k=3):
        self.busquedas += 1
        return [r for r in self.recs][:k]

    async def list_all(self, limit=200):
        return list(self.recs)

    async def delete(self, mid):
        antes = len(self.recs)
        self.recs = [r for r in self.recs if r["id"] != mid]
        return len(self.recs) < antes


# ── Memoria ───────────────────────────────────────────────────────────────

def test_generic_questions_do_not_pull_memories():
    """"¿Qué puedes hacer?" traía "me gusta el color negro" al prompt."""
    from app.core import prompt_builder as pb
    st = _Store(["Me gusta el color negro"])
    for q in ("¿Qué puedes hacer?", "hola", "What can you do?", "¿quién eres?"):
        p = pb.PromptParts(message=q)
        asyncio.run(pb.add_memory_async(p, q, None, st, False))
        assert "negro" not in p.memory, q
    assert st.busquedas == 0
    assert not pb.es_consulta_generica("¿qué coche me gustaba?")


def test_memory_block_says_to_use_it_only_if_relevant(tmp_path):
    from app.core import prompt_builder as pb
    from app.memory.profile import MemoryProfile
    perfil = MemoryProfile(tmp_path / "p.json")
    perfil.upsert_fact("nombre", "Me llamo Pau")
    p = pb.PromptParts(message="x")
    asyncio.run(pb.add_memory_async(p, "¿qué me recomiendas?", perfil, None, False))
    assert p.memory.startswith("LO QUE SABES DEL USUARIO") and "SOLO si es relevante" in p.memory


def test_semantic_hit_without_shared_words_needs_high_similarity(tmp_path, monkeypatch):
    import app.memory.store as ms
    s = ms.SemanticMemoryStore(db_path=str(tmp_path / "m.db"), ollama_url="http://x")

    async def emb(texto, kind="document"):
        # similitud ~0.6 con cualquier cosa: no debe bastar sin palabras en común
        return [1.0, 0.0] if kind == "query" else [0.6, 0.8]
    monkeypatch.setattr(s, "_embed", emb)
    asyncio.run(s.save("Me gusta el color negro", source="chat", category="preference"))
    assert asyncio.run(s.search("qué puedes hacer por mí", k=3)) == []
    assert ms.SEMANTIC_ONLY_MIN >= 0.7


def test_junk_in_semantic_store_is_purged_on_startup():
    from app.memory import semantic_setup as ss
    st = _Store(["Me gusta el color negro? lo odio.", "Trabajo en Aritex"])
    st.purge = lambda pred: _purge(st, pred)
    asyncio.run(ss.ensure_semantic_memory(type("S", (), {"ollama_base_url": "x"})(), st, intentos=0))
    assert [r["content"] for r in st.recs] == ["Trabajo en Aritex"]


async def _purge(st, pred):
    n = 0
    for r in list(st.recs):
        if pred(r["content"]) and await st.delete(r["id"]):
            n += 1
    return n


def test_deleting_in_settings_also_deletes_the_semantic_copy(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        store = c.app.state.memory_store

        async def _noemb(t, kind="document"):
            return None
        monkeypatch.setattr(store, "_embed", _noemb)
        c.app.state.memory_profile.upsert_fact("gustos:negro", "Me gusta el color negro")
        asyncio.run(store.save("Me gusta el color negro", source="chat", category="preference"))
        c.delete("/api/memory/profile/fact", params={"key": "gustos:negro"})
        assert not [r for r in asyncio.run(store.list_all()) if "negro" in r["content"]]


# ── Estilo de las respuestas ──────────────────────────────────────────────

def test_style_guide_is_prose_first_like_claude():
    from app.specialists.identity import ANDROMEDA_STYLE
    assert "Escribe en prosa clara por defecto" in ANDROMEDA_STYLE
    assert "Nunca listas dentro de listas" in ANDROMEDA_STYLE
    assert "análisis psicológicos" in ANDROMEDA_STYLE
    assert "títulos con ## para las secciones" not in ANDROMEDA_STYLE


# ── Potencia: mismo modelo, más o menos cómputo ───────────────────────────

def test_reasoning_follows_the_power_level():
    from app.core.reasoning import think_option
    assert think_option("qwen3:8b", "low") is False
    assert think_option("qwen3:14b", "high") is True
    assert think_option("gpt-oss:20b", "ultra") == "high"
    assert think_option("gpt-oss:20b", "mid") == "low"
    # modelos sin razonamiento: no se envía nada (Ollama devolvería error)
    for m in ("gemma3:27b", "llama3.1:8b", "qwen3-coder:30b", "phi3.5:3.8b"):
        assert think_option(m, "high") is None, m


def test_reasoning_is_sent_to_ollama():
    src = (ROOT / "backend/app/core/streaming.py").read_text(encoding="utf-8")
    assert '_reasoning.apply(payload, specialist.model_name, config.get("power_level"))' in src
    assert '"power_level":        locals().get("_chosen_level")' in (ROOT / "backend/app/routes/chat.py").read_text(encoding="utf-8")


def test_power_pack_scales_with_memory():
    from app.routes.models import power_pack_for
    assert set(power_pack_for(4)) == {"low", "mid"}
    assert power_pack_for(36)["high"] == "gemma3:27b" and "ultra" not in power_pack_for(36)
    assert "ultra" in power_pack_for(64)


def test_power_pack_endpoint_marks_installed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        primero = c.get("/api/models/power-pack").json()["levels"][0]["model"]
        c.app.state.registry.set_available_models([primero])
        d = c.get("/api/models/power-pack").json()
        assert d["levels"] and any(n["installed"] for n in d["levels"] if n["model"] == primero)
        assert d["missing_download_gb"] > 0


# ── Zoom de imágenes ──────────────────────────────────────────────────────

def test_image_zoom_uses_a_portal_and_the_full_image():
    mb = (SRC / "components/MessageBubble.jsx").read_text(encoding="utf-8")
    assert "<Portal>" in mb and "imagenesCompletas.get(src) || src" in mb
    assert "imagenesCompletas.set(m, images()[i])" in (SRC / "components/Chat.jsx").read_text(encoding="utf-8")
    assert "backdrop-filter: blur(28px)" in CSS


# ── MCP depurado y estado del usuario ─────────────────────────────────────

def test_mcp_catalog_is_curated():
    d = yaml.safe_load((ROOT / "config/mcp_servers.yaml").read_text(encoding="utf-8"))["servers"]
    for fuera in ("whatsapp", "memory", "everything", "puppeteer", "sequential-thinking",
                  "filesystem", "fetch", "time", "slack", "google-drive"):
        assert fuera not in d, fuera
    assert {"gmail", "google-calendar", "notion", "playwright"} <= set(d)


def test_mcp_state_lives_in_the_user_data_dir(tmp_path, monkeypatch):
    """En Windows el YAML está en Program Files: no se puede escribir."""
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from app.mcp import state
    state.set_enabled("notion", True)
    assert json.loads((tmp_path / "mcp_state.json").read_text(encoding="utf-8"))["enabled"]["notion"] is True
    cfg = state.apply({"servers": {"notion": {"enabled": False}}})
    assert cfg["servers"]["notion"]["enabled"] is True
    src = (ROOT / "backend/app/routes/mcp.py").read_text(encoding="utf-8")
    assert 'path.open("w"' not in src


# ── Animaciones y sugerencias ─────────────────────────────────────────────

def test_component_cards_spring_and_scroll_to_the_open_one():
    ch = (SRC / "components/ComponentsHealth.jsx").read_text(encoding="utf-8")
    assert "scrollIntoView({ behavior: 'smooth', block: 'center' })" in ch and "duration: 620" in ch
    assert "grid-auto-flow: row dense" in CSS


def test_power_panel_animates_its_height():
    chat = (SRC / "components/Chat.jsx").read_text(encoding="utf-8")
    assert '<div class="ias-wrap" classList={{ closing: cfgClosing() }}>' in chat
    assert "grid-template-rows: 0fr" in CSS


def test_suggestions_rotate_from_a_larger_pool():
    chat = (SRC / "components/Chat.jsx").read_text(encoding="utf-8")
    assert "Array.from({ length: 30 }" in chat and "setInterval" in chat
    assert "sort(() => Math.random() - 0.5)" not in chat
    i18n = (SRC / "stores/i18n.js").read_text(encoding="utf-8")
    assert i18n.count("'sug.30'") == 5


def test_listing_shows_the_user_state(tmp_path, monkeypatch):
    """Sin aplicar el estado, un conector activado aparecería como desactivado."""
    with _client(tmp_path, monkeypatch) as c:
        from app.mcp import state
        state.set_enabled("pandoc", True)
        listed = {s["id"]: s for s in c.get("/api/mcp/servers").json()["servers"]}
        assert listed["pandoc"]["enabled"] is True
