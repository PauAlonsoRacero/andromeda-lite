"""
Tests de robustez añadidos en el sprint de hardening:

- Extractor de memorias (patrones, topics, skip de preguntas)
- Actualización de memoria por topic (la nueva reemplaza la vieja)
- Recuperación de DB de memoria corrupta (backup + restore)
- Idempotencia de set_available_models (anti polling infinito)
- Debounce de should_refresh_tags
- Tool analytics del MetricsCollector (sanitización de params)

Todos autocontenidos: no dependen de Ollama ni de hardware real.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ── Extractor de memorias ───────────────────────────────────────────────────

def test_extractor_explicit_request():
    from app.memory.extractor import extract_memories
    out = extract_memories("recuerda que entrego el proyecto en 2 semanas")
    assert len(out) == 1
    content, cat, topic = out[0]
    assert "entrego el proyecto" in content.lower()
    assert cat == "explicit"


def test_extractor_skips_questions():
    from app.memory.extractor import extract_memories
    assert extract_memories("¿qué hora es?") == []
    assert extract_memories("crea un archivo txt") == []
    assert extract_memories("cómo estás") == []


def test_extractor_captures_topic():
    from app.memory.extractor import extract_memories
    out = extract_memories("trabajo con FastAPI y SolidJS")
    assert len(out) == 1
    _, _, topic = out[0]
    assert topic == "stack"


def test_extractor_name_and_language():
    from app.memory.extractor import extract_memories
    name = extract_memories("me llamo Pau")
    assert name and name[0][2] == "nombre"
    lang = extract_memories("háblame en catalán")
    assert lang and lang[0][2] == "idioma"


# ── Memoria: recuperación de corrupción ──────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_recovers_from_corruption(tmp_path):
    from app.memory.store import SemanticMemoryStore
    db = str(tmp_path / "mem.db")
    m = SemanticMemoryStore(db_path=db, ollama_url="http://x")
    await m.save(content="me llamo Pau", category="preference", source="auto:nombre")

    # Corromper la DB a propósito
    with open(db, "wb") as f:
        f.write(b"esto no es una base de datos sqlite valida")

    # Reabrir → debe recuperar del backup
    m2 = SemanticMemoryStore(db_path=db, ollama_url="http://x")
    mems = await m2.list_all(limit=10)
    assert any("Pau" in x["content"] for x in mems)


@pytest.mark.asyncio
async def test_memory_stats_has_new_fields(tmp_path):
    from app.memory.store import SemanticMemoryStore
    m = SemanticMemoryStore(db_path=str(tmp_path / "s.db"), ollama_url="http://x")
    await m.save(content="dato de prueba", category="general")
    stats = m.get_stats()
    assert "avg_content_chars" in stats
    assert "db_size_kb" in stats
    assert "search_hit_rate" in stats
    assert stats["total"] == 1


# ── Registry: idempotencia y debounce ────────────────────────────────────────

def test_set_available_models_idempotent():
    from app.specialists.registry import SpecialistRegistry
    reg = SpecialistRegistry.__new__(SpecialistRegistry)
    reg._available_models = set()
    reg._auto_activated_once = False
    # Primera vez: cambia
    reg.set_available_models(["a", "b"])
    assert reg._available_models == {"a", "b"}
    # Misma lista: no-op (no peta, sigue igual)
    reg.set_available_models(["a", "b"])
    assert reg._available_models == {"a", "b"}
    # Lista distinta: actualiza
    reg.set_available_models(["a", "b", "c"])
    assert reg._available_models == {"a", "b", "c"}


def test_should_refresh_tags_debounce():
    from app.specialists.registry import SpecialistRegistry
    reg = SpecialistRegistry.__new__(SpecialistRegistry)
    # Primera llamada: True (nunca refrescó)
    assert reg.should_refresh_tags(min_interval_s=30) is True
    # Inmediatamente después: False (debounce)
    assert reg.should_refresh_tags(min_interval_s=30) is False


# ── Tool analytics ───────────────────────────────────────────────────────────

def test_tool_analytics_sanitizes_params():
    from app.observability.metrics import MetricsCollector
    mc = MetricsCollector()
    mc.record_tool_call(
        name="write_file", latency_ms=12.5, success=True,
        params={"path": "x.txt", "content": "datos super secretos y largos"},
    )
    summary = mc.get_tool_summary()
    assert summary["total_calls"] == 1
    assert "write_file" in summary["by_tool"]
    # El contenido real NO debe aparecer; solo el tipo y tamaño
    recent = summary["recent"][0]
    assert "secretos" not in str(recent["params"])
    assert "chars" in recent["params"]["content"]


def test_tool_analytics_error_rate():
    from app.observability.metrics import MetricsCollector
    mc = MetricsCollector()
    mc.record_tool_call(name="read_file", latency_ms=5, success=True)
    mc.record_tool_call(name="read_file", latency_ms=5, success=False, error="no existe")
    summary = mc.get_tool_summary()
    assert summary["by_tool"]["read_file"]["calls"] == 2
    assert summary["by_tool"]["read_file"]["error_rate"] == 0.5


# ── Herramientas nativas de archivo: nuevas operaciones + seguridad ──────────

@pytest.mark.asyncio
async def test_builtin_file_operations(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.mcp.builtin_tools import call_builtin
    # write → append → edit → read
    await call_builtin("write_file", {"path": "a.txt", "content": "uno\n"})
    await call_builtin("append_file", {"path": "a.txt", "content": "dos\n"})
    await call_builtin("edit_file", {"path": "a.txt", "find": "uno", "replace": "UNO"})
    r = await call_builtin("read_file", {"path": "a.txt"})
    assert "UNO" in r.content[0]["text"] and "dos" in r.content[0]["text"]
    # make_dir + delete
    await call_builtin("make_dir", {"path": "carpeta"})
    r = await call_builtin("delete_file", {"path": "a.txt"})
    assert not r.is_error
    assert not (tmp_path / "a.txt").exists()


@pytest.mark.asyncio
async def test_builtin_path_traversal_blocked(tmp_path, monkeypatch):
    """SEGURIDAD: no se puede leer fuera del workspace con ../"""
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    from app.mcp.builtin_tools import call_builtin, _safe_path
    # Un escape se reancla dentro del root
    p = _safe_path("../../../etc/passwd")
    assert str(tmp_path) in str(p)
    assert "etc/passwd" not in str(p) or str(p).startswith(str(tmp_path))
    # Leerlo no devuelve el passwd del sistema
    r = await call_builtin("read_file", {"path": "../../../etc/passwd"})
    text = r.content[0]["text"] if r.content else ""
    assert "root:x:0:0" not in text


@pytest.mark.asyncio
async def test_builtin_run_command_gated(tmp_path, monkeypatch):
    """run_command está deshabilitado salvo opt-in, y bloquea destructivos."""
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ANDROMEDA_ALLOW_SHELL", raising=False)
    from app.mcp.builtin_tools import call_builtin, builtin_tools
    # Sin opt-in: no aparece en la lista y falla si se invoca
    names = [t.name for t in builtin_tools()]
    assert "run_command" not in names
    r = await call_builtin("run_command", {"command": "ls"})
    assert r.is_error
    # Con opt-in: aparece, ejecuta seguros, bloquea destructivos
    monkeypatch.setenv("ANDROMEDA_ALLOW_SHELL", "1")
    assert "run_command" in [t.name for t in builtin_tools()]
    r = await call_builtin("run_command", {"command": "echo hola"})
    assert not r.is_error and "hola" in r.content[0]["text"]
    r = await call_builtin("run_command", {"command": "rm -rf /"})
    assert r.is_error


# ── Extractor de memoria: sin duplicados, sin coletillas (bug real) ──────────

def test_extractor_no_duplicate_language_preference():
    """'prefiero que me hables en inglés, guardalo en memoria' → 1 sola entrada."""
    from app.memory.extractor import extract_memories
    r = extract_memories("prefiero que me hables en inglés, guardalo en la memoria si puedes")
    assert len(r) == 1, f"esperaba 1, salieron {len(r)}: {r}"
    content, cat, topic = r[0]
    assert topic == "idioma"
    # La coletilla NO debe estar en el contenido guardado
    assert "memoria" not in content.lower()
    assert "guardalo" not in content.lower()


def test_extractor_specific_beats_generic():
    """Un patrón específico (nombre) no se duplica con 'preferencia' genérica."""
    from app.memory.extractor import extract_memories
    r = extract_memories("me llamo Pau")
    assert len(r) == 1 and r[0][2] == "nombre"


def test_extractor_ignores_questions():
    from app.memory.extractor import extract_memories
    assert extract_memories("¿puedes crear un archivo?") == []
