"""Memoria por significado activada de base (sin instalar nada a mano)."""
import asyncio
import json
import sqlite3
import types

import pytest


class _Resp:
    def __init__(self, status=200, data=None, lineas=()):
        self.status_code, self._data, self._lineas = status, data or {}, lineas

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    async def aiter_lines(self):
        for l in self._lineas:
            yield l

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeOllama:
    """Ollama sin el modelo de embeddings; lo "instala" al pedir la descarga."""
    def __init__(self):
        self.instalado, self.descargas = False, []

    def cliente(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        modelos = [{"name": "qwen3:8b"}] + ([{"name": "nomic-embed-text:latest"}] if self.instalado else [])
        return _Resp(data={"models": modelos})

    def stream(self, method, url, json=None, **k):
        self.descargas.append(json["model"])
        self.instalado = True
        return _Resp(lineas=['{"total": 10, "completed": 5}', '{"status": "success"}'])

    @property
    def is_closed(self):
        return False

    async def post(self, url, json=None, **k):
        if not self.instalado:
            return _Resp(status=404)
        return _Resp(data={"embedding": [1.0, 0.5, float(len(json["prompt"]) % 5)]})


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    import app.core.flags as flags
    import app.memory.semantic_setup as ss
    import app.memory.store as st
    import app.ollama_resolver as orv
    ollama = _FakeOllama()

    async def resolver(u):
        return "http://ollama"
    monkeypatch.setattr(orv, "resolve_ollama_url", resolver)
    monkeypatch.setattr(ss.httpx, "AsyncClient", ollama.cliente)
    monkeypatch.setattr(st, "_cliente_http", lambda: ollama)
    monkeypatch.setattr(flags, "get_flag", lambda s, k: True)
    store = st.SemanticMemoryStore(db_path=str(tmp_path / "m.db"), ollama_url="http://ollama")
    return ss, st, store, ollama


def _vacios(store):
    return sqlite3.connect(store.db_path).execute(
        "SELECT COUNT(*) FROM memories WHERE embedding='[]'").fetchone()[0]


def test_model_is_downloaded_and_old_memories_backfilled(entorno):
    ss, st, store, ollama = entorno
    for t in ("Me gusta el Audi TT", "Trabajo en Aritex"):
        asyncio.run(store.save(t, source="chat", category="fact"))
    assert _vacios(store) == 2, "sin modelo, los recuerdos se guardan sin vector"
    asyncio.run(ss.ensure_semantic_memory(types.SimpleNamespace(ollama_base_url="x"), store,
                                          intentos=1, espera_s=0))
    assert ollama.descargas == [st.EMBED_MODEL]
    assert ss.STATE["status"] == "ready" and ss.STATE["backfilled"] == 2
    assert _vacios(store) == 0


def test_no_download_when_network_is_disabled(entorno, monkeypatch):
    ss, st, store, ollama = entorno
    import app.core.flags as flags
    monkeypatch.setattr(flags, "get_flag", lambda s, k: False)
    asyncio.run(ss.ensure_semantic_memory(types.SimpleNamespace(ollama_base_url="x"), store,
                                          intentos=1, espera_s=0))
    assert ollama.descargas == [] and ss.STATE["status"] == "offline"


def test_nomic_task_prefixes_are_used(entorno):
    ss, st, store, ollama = entorno
    ollama.instalado = True
    enviados = []
    orig = ollama.post

    async def espia(url, json=None, **k):
        enviados.append(json["prompt"])
        return await orig(url, json=json, **k)
    ollama.post = espia
    asyncio.run(store.save("Me gusta el Audi TT", source="chat", category="fact"))
    asyncio.run(store.search("qué coche me gustaba", k=1))
    assert enviados[0].startswith("search_document: ")
    assert enviados[1].startswith("search_query: ")


def test_old_vectors_are_recomputed_once_when_scheme_changes(entorno):
    ss, st, store, ollama = entorno
    ollama.instalado = True
    asyncio.run(store.save("Recuerdo antiguo", source="chat", category="fact"))
    assert store.ensure_embed_scheme() == 1          # primera vez: se recalculan
    assert store.ensure_embed_scheme() == 0          # después, nunca más


def test_threshold_allows_related_but_reworded_matches():
    from app.memory.store import SIMILARITY_THRESHOLD
    assert SIMILARITY_THRESHOLD <= 0.6


def test_startup_launches_it_outside_tests():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "backend/app/__init__.py").read_text(encoding="utf-8")
    i_store = src.index("app.state.memory_store = memory_store")
    i_spawn = src.index("ensure_semantic_memory(settings")
    assert i_store < i_spawn, "se lanza antes de que exista el almacén"


def test_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        d = c.get("/api/memory/semantic").json()
        assert d["model"] == "nomic-embed-text" and "status" in d


def test_profile_facts_are_not_repeated_as_memories(tmp_path):
    from app.core import prompt_builder as pb
    from app.memory.profile import MemoryProfile

    class _Store:
        async def search(self, q, k=3):
            return [{"content": "me gusta el audi tt"}, {"content": "Tiene un perro llamado Max"}]
    perfil = MemoryProfile(tmp_path / "p.json")
    perfil.upsert_fact("gustos:audi", "Me gusta el Audi TT")
    p = pb.PromptParts(message="x")
    asyncio.run(pb.add_memory_async(p, "coches", perfil, _Store(), False))
    assert p.memory.lower().count("audi tt") == 1
    assert "perro llamado Max" in p.memory
