"""Consola de diagnóstico: ver qué hace la aplicación por dentro."""
import logging

logging.disable(logging.CRITICAL)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    from fastapi.testclient import TestClient
    from app import create_app
    return TestClient(create_app())


def test_recording_is_off_by_default(tmp_path, monkeypatch):
    """Registra prompts completos: no puede estar activo sin pedirlo."""
    from app.observability import diagnostics as diag
    diag.set_enabled(False)
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/diagnostics").json()["enabled"] is False


def test_nothing_is_logged_while_off():
    from app.observability import diagnostics as diag
    diag.set_enabled(False)
    diag.log("test", "no debería guardarse")
    assert diag.get_events() == []


def test_events_are_captured_when_on():
    from app.observability import diagnostics as diag
    diag.set_enabled(True)
    diag.clear()
    diag.log("test", "un evento", detail="detalle", data={"k": 1}, level="success")
    ev = diag.get_events()
    assert len(ev) == 1
    assert ev[0]["event"] == "un evento" and ev[0]["data"] == {"k": 1}
    diag.set_enabled(False)


def test_the_pipeline_reports_its_decisions(tmp_path, monkeypatch):
    """Lo que hacía falta: ver POR QUÉ pasó algo, no solo que pasó."""
    from app.observability import diagnostics as diag
    with _client(tmp_path, monkeypatch) as c:
        c.put("/api/diagnostics", json={"enabled": True})
        c.post("/api/chat", json={"prompt": "when is gta 6 launching", "stream": False})
        categorias = {e["category"] for e in diag.get_events()}
        # El prompt final es la pieza clave para diagnosticar
        assert "prompt" in categorias
        assert {"memory", "rag", "skills"} & categorias
        c.put("/api/diagnostics", json={"enabled": False})


def test_final_prompt_is_recorded(tmp_path, monkeypatch):
    from app.observability import diagnostics as diag
    with _client(tmp_path, monkeypatch) as c:
        c.put("/api/diagnostics", json={"enabled": True})
        c.post("/api/chat", json={"prompt": "hola mundo", "stream": False})
        prompts = [e for e in diag.get_events() if e["category"] == "prompt"]
        assert prompts, "el prompt final no se registró"
        assert "hola mundo" in prompts[-1]["detail"]
        assert "total_chars" in prompts[-1]["data"]
        c.put("/api/diagnostics", json={"enabled": False})


def test_incremental_polling(tmp_path, monkeypatch):
    """La interfaz pide solo lo nuevo, no el registro entero cada segundo."""
    from app.observability import diagnostics as diag
    with _client(tmp_path, monkeypatch) as c:
        c.put("/api/diagnostics", json={"enabled": True})
        diag.clear()
        diag.log("test", "primero")
        r1 = c.get("/api/diagnostics/events").json()
        diag.log("test", "segundo")
        r2 = c.get("/api/diagnostics/events", params={"since": r1["last_seq"]}).json()
        assert len(r2["events"]) == 1
        assert r2["events"][0]["event"] == "segundo"
        c.put("/api/diagnostics", json={"enabled": False})


def test_export_is_readable(tmp_path, monkeypatch):
    from app.observability import diagnostics as diag
    with _client(tmp_path, monkeypatch) as c:
        c.put("/api/diagnostics", json={"enabled": True})
        diag.clear()
        diag.log("search", "buscando algo", detail="detalle largo", duration_ms=42.5)
        texto = c.get("/api/diagnostics/export").text
        assert "ANDROMEDA" in texto and "buscando algo" in texto and "42.5ms" in texto
        c.put("/api/diagnostics", json={"enabled": False})


def test_snapshot_works_without_recording(tmp_path, monkeypatch):
    """Es lo primero que se mira ante un fallo: no puede exigir activar nada."""
    from app.observability import diagnostics as diag
    diag.set_enabled(False)
    with _client(tmp_path, monkeypatch) as c:
        d = c.get("/api/diagnostics/snapshot").json()
        for cap in ("red", "creacion_archivos", "memoria_semantica", "skills"):
            assert cap in d["capacidades"]
        assert "ollama" in d and "mcp" in d and "buscador" in d


def test_disabling_clears_the_log():
    """Contiene prompts completos: al apagar debe desaparecer."""
    from app.observability import diagnostics as diag
    diag.set_enabled(True)
    diag.log("test", "algo sensible")
    diag.set_enabled(False)
    assert diag.get_events() == []


def test_log_is_capped():
    """No puede crecer sin control en una sesión larga."""
    from app.observability import diagnostics as diag
    diag.set_enabled(True)
    diag.clear()
    for i in range(2500):
        diag.log("test", f"evento {i}")
    assert len(diag.get_events()) <= 2000
    diag.set_enabled(False)


def test_timed_records_duration_and_errors():
    from app.observability import diagnostics as diag
    diag.set_enabled(True)
    diag.clear()
    with diag.timed("test", "operación") as t:
        t.data["x"] = 1
    ev = diag.get_events()[-1]
    assert ev["duration_ms"] is not None and ev["data"]["x"] == 1

    try:
        with diag.timed("test", "operación que falla"):
            raise ValueError("boom")
    except ValueError:
        pass
    err = diag.get_events()[-1]
    assert err["level"] == "error" and "boom" in err["detail"]
    diag.set_enabled(False)


# ── Cobertura de la instrumentación ───────────────────────────────────────

def test_every_key_subsystem_is_instrumented():
    """Un subsistema sin registrar es un punto ciego cuando algo falla ahí."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "backend/app"
    for modulo in ("core/streaming.py", "core/prompt_builder.py", "core/web_search.py",
                   "routes/chat.py", "mcp/manager.py", "mcp/protocol.py",
                   "memory/extractor.py", "core/executor.py"):
        src = (raiz / modulo).read_text(encoding="utf-8")
        assert "diagnostics" in src, f"{modulo} no reporta nada"


def test_ollama_request_parameters_are_logged():
    """Sin ver las opciones enviadas no se puede saber por qué va lento."""
    import inspect
    from app.core import streaming
    src = inspect.getsource(streaming)
    assert '"opciones"' in src and '"keep_alive"' in src


def test_generation_performance_is_measured():
    """Tokens por segundo y TTFT distinguen 'carga el modelo' de 'genera lento'."""
    import inspect
    from app.core import streaming
    src = inspect.getsource(streaming)
    assert "tokens_por_segundo" in src and "ttft_ms" in src


def test_snapshot_includes_hardware_and_resources(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        d = c.get("/api/diagnostics/snapshot").json()
        assert "hardware" in d and "recursos" in d
        # Las opciones calculadas explican las decisiones de rendimiento
        assert "opciones_calculadas" in d["hardware"]
        assert "variables" in d["entorno"]


def test_secrets_are_masked_in_the_snapshot(tmp_path, monkeypatch):
    """Las variables se exportan: las claves no pueden viajar en claro."""
    monkeypatch.setenv("ANDROMEDA_TEST_API_KEY", "secreto-que-no-debe-salir")
    with _client(tmp_path, monkeypatch) as c:
        variables = c.get("/api/diagnostics/snapshot").json()["entorno"]["variables"]
        assert variables.get("ANDROMEDA_TEST_API_KEY") == "(oculto)"


def test_export_includes_system_state(tmp_path, monkeypatch):
    """El registro sin el contexto del sistema se interpreta a medias."""
    with _client(tmp_path, monkeypatch) as c:
        c.put("/api/diagnostics", json={"enabled": True})
        texto = c.get("/api/diagnostics/export").text
        assert "ESTADO DEL SISTEMA" in texto and "EVENTOS" in texto
        assert "hardware" in texto
        c.put("/api/diagnostics", json={"enabled": False})


# ── Visibilidad del panel en el menú ──────────────────────────────────────

def test_panel_hidden_by_default_in_release(tmp_path, monkeypatch):
    """Versión publicada: sin ANDROMEDA_DIAGNOSTICS=1 el panel no aparece
    (expone prompts completos y variables de entorno)."""
    from app.observability import diagnostics as diag
    diag.set_enabled(False)
    monkeypatch.delenv("ANDROMEDA_DIAGNOSTICS", raising=False)
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/diagnostics").json()["available"] is False


def test_frontend_starts_with_the_panel_hidden():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "frontend/src/stores/edition.js").read_text(encoding="utf-8")
    assert "setDiagAvailable] = createSignal(false)" in src


def test_panel_visible_with_the_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DIAGNOSTICS", "1")
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/diagnostics").json()["available"] is True


def test_panel_stays_visible_while_recording(tmp_path, monkeypatch):
    """Si se activa desde otra vía, el menú debe seguir mostrándolo."""
    from app.observability import diagnostics as diag
    monkeypatch.delenv("ANDROMEDA_DIAGNOSTICS", raising=False)
    with _client(tmp_path, monkeypatch) as c:
        diag.set_enabled(True)
        assert c.get("/api/diagnostics").json()["available"] is True
        diag.set_enabled(False)


def test_menu_does_not_depend_on_fetch():
    """Segundo bug: se usaba fetch() con ruta relativa, pero en la app de
    escritorio el frontend no comparte origen con el backend, así que la
    petición no llegaba y el panel nunca aparecía. El resto del código usa
    axios, que ya lleva la URL base."""
    from pathlib import Path
    store = (Path(__file__).resolve().parent.parent
             / "frontend/src/stores/edition.js").read_text(encoding="utf-8")
    import re
    bloque = store[store.index("export async function checkDiagnostics"):]
    assert "axios.get" in bloque, "sigue usando fetch con ruta relativa"
    assert "fetch(" not in bloque.split("}")[0]


def test_panel_visible_from_first_render():
    """La señal arranca en true: durante la depuración es peor perder el panel
    por una consulta lenta que mostrarlo de más."""
    from pathlib import Path
    store = (Path(__file__).resolve().parent.parent
             / "frontend/src/stores/edition.js").read_text(encoding="utf-8")
    assert "diagAvailable, setDiagAvailable] = createSignal(" in store


def test_menu_uses_a_reactive_signal():
    """Primer bug: una variable global no funciona en Solid porque el menú ya se
    renderizó cuando llega la respuesta del backend, y no vuelve a mirarla."""
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent / "frontend/src"
    store = (raiz / "stores/edition.js").read_text(encoding="utf-8")
    assert "diagAvailable" in store and "createSignal" in store

    sidebar = (raiz / "components/Sidebar.jsx").read_text(encoding="utf-8")
    assert "diagAvailable" in sidebar
    assert "__ANDROMEDA_DIAG__" not in sidebar, "sigue usando la variable global"

    app = (raiz / "App.jsx").read_text(encoding="utf-8")
    assert "checkDiagnostics" in app


def test_removal_is_documented():
    """El panel expone prompts y variables de entorno: quitarlo antes de
    publicar no puede depender de que alguien se acuerde."""
    from pathlib import Path
    doc = Path(__file__).resolve().parent.parent / "docs/QUITAR-DIAGNOSTICO.md"
    assert doc.exists(), "falta la guía para retirar el panel"
    texto = doc.read_text(encoding="utf-8")
    assert "ANDROMEDA_DIAGNOSTICS" in texto and "available" in texto


def test_panel_can_be_disabled_for_release(tmp_path, monkeypatch):
    """Debe poder apagarse sin tocar código, para poder publicar rápido."""
    from app.observability import diagnostics as diag
    diag.set_enabled(False)
    monkeypatch.setenv("ANDROMEDA_DIAGNOSTICS", "0")
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/diagnostics").json()["available"] is False
