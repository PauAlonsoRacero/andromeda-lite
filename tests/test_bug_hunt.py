"""Búsqueda de bugs y rendimiento: tareas sueltas, bloqueos, reactividad."""
import asyncio
import glob
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "backend/app"
SRC = ROOT / "frontend/src"


# ── Backend ────────────────────────────────────────────────────────────────

def test_no_fire_and_forget_tasks():
    """asyncio.create_task sin guardar la referencia: el recolector puede
    destruir la tarea a mitad (la descarga de modelos se quedaba congelada)."""
    sueltas = []
    for f in glob.glob(str(APP / "**/*.py"), recursive=True):
        if f.endswith("core/background.py"):
            continue   # es la implementación que guarda la referencia
        for n, linea in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*asyncio\.create_task\(", linea):
                sueltas.append(f"{Path(f).relative_to(ROOT)}:{n}")
    assert not sueltas, sueltas


def test_spawn_keeps_tasks_alive_and_logs_errors(caplog):
    import logging
    from app.core import background
    logging.disable(logging.NOTSET)   # otros módulos de test silencian el logging
    caplog.set_level(logging.WARNING, logger="andromeda.background")

    async def main():
        antes = background.pending()
        hecho = []

        async def ok():
            await asyncio.sleep(0.01)
            hecho.append(1)

        async def falla():
            raise ValueError("boom")
        background.spawn(ok())
        background.spawn(falla(), name="tarea-que-falla")
        assert background.pending() == antes + 2
        await asyncio.sleep(0.05)
        return hecho
    assert asyncio.run(main()) == [1]
    assert "tarea-que-falla" in caplog.text


def test_no_blocking_sleep_in_async_routes():
    """time.sleep en una ruta async congela el servidor entero."""
    for f in glob.glob(str(APP / "routes/*.py")):
        src = Path(f).read_text(encoding="utf-8")
        for m in re.finditer(r"async def \w+\(.*?(?=\nasync def |\ndef |\Z)", src, re.S):
            assert "time.sleep(" not in m.group(0), f


def test_embedding_client_is_reused():
    """Un cliente nuevo por llamada costaba ~20 ms en cada mensaje."""
    from app.memory import store

    async def main():
        return store._cliente_http() is store._cliente_http()
    assert asyncio.run(main())


def test_missing_embedding_model_is_not_retried_every_message(tmp_path, monkeypatch):
    import httpx
    from app.memory.store import SemanticMemoryStore
    llamadas = []

    class _Resp:
        status_code = 404

    class _Cli:
        is_closed = False

        async def post(self, *a, **k):
            llamadas.append(1)
            return _Resp()
    import app.memory.store as st
    monkeypatch.setattr(st, "_cliente_http", lambda: _Cli())
    s = SemanticMemoryStore(db_path=str(tmp_path / "m.db"), ollama_url="http://x")
    for _ in range(5):
        assert asyncio.run(s._embed("hola")) is None
    assert len(llamadas) == 1, "reintenta el modelo no instalado en cada mensaje"


def test_public_searxng_is_paused_after_failing(monkeypatch):
    import app.core.web_search as ws
    intentos = []

    async def falla(q, n, t):
        intentos.append(1)
        raise RuntimeError("403")
    monkeypatch.setattr(ws, "_search_searxng_intento", falla)
    monkeypatch.setattr(ws, "_searxng_pausa_hasta", 0.0)
    monkeypatch.delenv("ANDROMEDA_SEARXNG_URL", raising=False)
    for _ in range(3):
        try:
            asyncio.run(ws._search_searxng("x", 3, 1.0))
        except RuntimeError:
            pass
    assert len(intentos) == 1, "vuelve a probar las instancias públicas en cada búsqueda"


def test_search_tries_last_working_engine_first(monkeypatch):
    import app.core.web_search as ws
    orden = []

    def motor(nombre, res):
        async def f(q, n, t):
            orden.append(nombre)
            if res is None:
                raise RuntimeError("x")
            return res
        return f
    monkeypatch.setattr(ws, "_ultimo_motor_ok", None)
    monkeypatch.setattr(ws, "_searxng_pausa_hasta", time.monotonic() + 999)
    monkeypatch.setattr(ws, "_search_ddg_lite", motor("lite", []))
    monkeypatch.setattr(ws, "_search_ddg_html", motor("html", [{"title": "T", "snippet": "", "url": "https://a.com"}]))
    asyncio.run(ws.search_web("gta 6"))
    orden.clear()
    asyncio.run(ws.search_web("gta 6"))
    assert orden == ["html"], orden


# ── Frontend: reactividad ──────────────────────────────────────────────────

def test_message_metadata_is_reactive():
    """Leído una sola vez: sin archivo creado, sin latencia y votos sin request_id."""
    b = (SRC / "components/MessageBubble.jsx").read_text(encoding="utf-8")
    assert "const meta      = () => message.metadata" in b
    assert "request_id: meta()?.request_id" in b
    assert not re.search(r"\bmeta\?\.", b), "queda algún acceso no reactivo a meta"


def test_error_state_is_reactive():
    b = (SRC / "components/MessageBubble.jsx").read_text(encoding="utf-8")
    assert "const isError   = () => message.error" in b


def test_trace_viewer_has_no_early_return():
    t = (SRC / "components/TraceViewer.jsx").read_text(encoding="utf-8")
    assert not re.search(r"^\s*if \(!trace\(\)\) return null", t, re.M)


# ── Segunda pasada ────────────────────────────────────────────────────────

def test_mac_free_memory_does_not_run_system_profiler_each_time(monkeypatch):
    """system_profiler (0,3-1 s) se ejecutaba en CADA mensaje antes de generar,
    y además devolvía siempre el 75 % del total."""
    import app.hardware.detector as d
    cls = next(v for v in vars(d).values() if isinstance(v, type) and hasattr(v, "get_current_vram_free"))
    inst = cls()
    llamadas = []
    monkeypatch.setattr(inst, "_detect_apple", lambda: (llamadas.append(1), [{"vram_total_gb": 44.0}])[1])
    monkeypatch.setattr(d.sys, "platform", "darwin")
    monkeypatch.setattr(d, "_APPLE_VRAM_TOTAL", None)
    for _ in range(20):
        v = inst.get_current_vram_free()
    assert len(llamadas) == 1
    assert 0 < v <= 44.0


def test_flags_are_cached_but_see_changes(tmp_path, monkeypatch):
    from app.core import flags
    ruta = tmp_path / "flags.json"
    monkeypatch.setattr(flags, "_state_path", lambda s: ruta)
    ruta.write_text('{"a": true}')
    assert flags._load(None) == {"a": True}
    ruta.write_text('{"a": false, "b": true}')   # cambio inmediato
    assert flags._load(None) == {"a": False, "b": True}


def test_conversation_history_keeps_more_than_20():
    chat = (SRC / "stores/chat.js").read_text(encoding="utf-8")
    assert "const MAX_CONVERSATIONS = 100" in chat and "MAX_BYTES" in chat


def test_state_files_are_written_atomically(tmp_path):
    from app.core.fsutil import atomic_write_text
    p = tmp_path / "prefs.json"
    atomic_write_text(p, '{"x": 1}')
    assert p.read_text() == '{"x": 1}' and not (tmp_path / "prefs.json.tmp").exists()
    src = (APP / "routes/settings_routes.py").read_text(encoding="utf-8")
    assert "atomic_write_text(_prefs_path()" in src


def test_system_panel_closing_animation_is_reactive():
    s = (SRC / "components/SystemStatus.jsx").read_text(encoding="utf-8")
    assert "props.closing" in s and "function SystemStatus({" not in s
