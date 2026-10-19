"""Compactación de contexto: resumir lo antiguo en vez de descartarlo."""
import asyncio


def _hist(n, filler="palabra "):
    """Historial sintético largo, con un dato concreto al principio."""
    h = [{"role": "user", "content": "El proyecto se llama Andromeda y el puerto es el 8765."}]
    for i in range(n):
        h.append({"role": "assistant", "content": filler * 60})
        h.append({"role": "user", "content": f"Mensaje {i} " + filler * 40})
    return h


def test_no_compaction_when_history_fits():
    from app.core.compaction import compact_history
    short = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "qué tal"}]
    out, info = asyncio.run(compact_history(short, budget_tokens=5000))
    assert out == short and info["compacted"] is False


def test_compaction_triggers_and_shrinks_context():
    from app.core.compaction import compact_history, history_tokens
    long_hist = _hist(20)
    out, info = asyncio.run(compact_history(long_hist, budget_tokens=300))
    assert info["compacted"] is True
    assert len(out) < len(long_hist)
    assert history_tokens(out) < history_tokens(long_hist)


def test_compaction_preserves_recent_messages_verbatim():
    from app.core.compaction import compact_history
    long_hist = _hist(20)
    out, _ = asyncio.run(compact_history(long_hist, budget_tokens=300))
    assert out[-1]["content"] == long_hist[-1]["content"]     # el último, intacto
    assert out[0]["role"] == "system"                          # el resumen va delante


def test_extractive_summary_keeps_concrete_data():
    """Sin Ollama, el resumen local debe conservar cifras y nombres."""
    from app.core.compaction import _extractive_summary
    msgs = [
        {"role": "user", "content": "El servidor escucha en el puerto 8765 y usa FastAPI."},
        {"role": "assistant", "content": "vale"},
        {"role": "user", "content": "Vamos a desplegar la version 2.3 en Kubernetes el lunes."},
    ]
    summary = _extractive_summary(msgs)
    assert "8765" in summary and "2.3" in summary
    assert "vale" not in summary.lower().split(":")[-1][:10]   # relleno descartado


def test_compaction_never_crashes_without_ollama():
    """Sin Ollama, cae al resumen extractivo sin lanzar excepción."""
    from app.core.compaction import compact_history
    out, info = asyncio.run(compact_history(
        _hist(15), budget_tokens=200,
        ollama_url="http://127.0.0.1:1", model="noexiste"))
    assert info["compacted"] is True
    assert info["source"] in ("extractive", "truncated")
    assert out


def test_needs_compaction_thresholds():
    from app.core.compaction import needs_compaction
    assert needs_compaction([], 100) is False
    assert needs_compaction(_hist(20), 100000) is False        # cabe de sobra
    assert needs_compaction(_hist(20), 100) is True
