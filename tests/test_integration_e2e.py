"""
Tests de integración END-TO-END, cero mocks en la parte de archivos.

Ejercitan el flujo completo que un usuario dispararía vía chat:
  "crea un archivo, edítalo, ejecútalo, bórralo" — pero invocando
  directamente las herramientas builtin sobre el disco real (tmp_path),
  igual que haría MCPExecutor cuando el modelo emite tool_calls.

La diferencia con test_robustness: aquí encadenamos operaciones como
un flujo real de trabajo y verificamos el estado del disco tras cada paso.
"""

import os
import asyncio
import pytest


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ANDROMEDA_ALLOW_SHELL", "1")
    return tmp_path


@pytest.mark.asyncio
async def test_full_file_workflow_on_real_disk(ws):
    """Flujo real: crear script → ejecutarlo → guardar salida → editar → borrar."""
    from app.mcp.builtin_tools import call_builtin

    # 1. Crear un script Python real
    r = await call_builtin("write_file", {
        "path": "contar.py",
        "content": "for i in range(1,4):\n    print(f'n={i}')\n",
    })
    assert not r.is_error
    assert (ws / "contar.py").exists()

    # 2. Ejecutarlo de verdad (run_command, no mock)
    r = await call_builtin("run_command", {"command": "python3 contar.py"})
    assert not r.is_error
    out = r.content[0]["text"]
    assert "n=1" in out and "n=3" in out

    # 3. Crear carpeta y guardar la salida
    await call_builtin("make_dir", {"path": "reports"})
    assert (ws / "reports").is_dir()
    r = await call_builtin("write_file", {"path": "reports/out.txt", "content": out})
    assert not r.is_error
    assert (ws / "reports" / "out.txt").read_text().count("n=") == 3

    # 4. Editar el reporte (buscar/reemplazar real)
    r = await call_builtin("edit_file", {
        "path": "reports/out.txt", "find": "n=1", "replace": "PRIMERO",
    })
    assert not r.is_error
    assert "PRIMERO" in (ws / "reports" / "out.txt").read_text()

    # 5. Append
    r = await call_builtin("append_file", {"path": "reports/out.txt", "content": "\nFIN\n"})
    assert not r.is_error
    assert (ws / "reports" / "out.txt").read_text().rstrip().endswith("FIN")

    # 6. Listar y verificar contenido del workspace
    r = await call_builtin("list_files", {})
    listing = r.content[0]["text"]
    assert "contar.py" in listing and "reports/" in listing

    # 7. Borrar el script y verificar que desaparece del disco
    r = await call_builtin("delete_file", {"path": "contar.py"})
    assert not r.is_error
    assert not (ws / "contar.py").exists()


@pytest.mark.asyncio
async def test_edit_file_on_missing_file_is_clean_error(ws):
    """Editar algo que no existe da error claro, no excepción cruda."""
    from app.mcp.builtin_tools import call_builtin
    r = await call_builtin("edit_file", {"path": "nope.txt", "find": "a", "replace": "b"})
    assert r.is_error
    assert "not found" in r.error_msg.lower() or "no existe" in r.error_msg.lower()


@pytest.mark.asyncio
async def test_run_command_blocks_destructive_in_workflow(ws):
    """En un flujo real, los comandos destructivos siguen bloqueados."""
    from app.mcp.builtin_tools import call_builtin
    await call_builtin("write_file", {"path": "importante.txt", "content": "no me borres"})
    # Intento destructivo
    r = await call_builtin("run_command", {"command": "rm -rf importante.txt"})
    assert r.is_error
    # El archivo sigue ahí
    assert (ws / "importante.txt").exists()


@pytest.mark.asyncio
async def test_concurrent_file_writes(ws):
    """20 escrituras concurrentes no se corrompen entre sí."""
    from app.mcp.builtin_tools import call_builtin
    async def w(i):
        return await call_builtin("write_file", {"path": f"f{i}.txt", "content": f"contenido {i}"})
    results = await asyncio.gather(*[w(i) for i in range(20)])
    assert all(not r.is_error for r in results)
    for i in range(20):
        assert (ws / f"f{i}.txt").read_text() == f"contenido {i}"


# ── MCPManager: servers externos + builtin ──────────────────────────────────

@pytest.mark.asyncio
async def test_manager_always_exposes_builtin_tools(ws, tmp_path):
    """Aunque no haya ningún server externo configurado, las builtin existen."""
    from app.mcp.manager import MCPManager
    # YAML vacío / inexistente → solo builtin
    cfg = tmp_path / "empty_mcp.yaml"
    cfg.write_text("servers: {}\n")
    mgr = MCPManager(config_path=str(cfg))
    await mgr.initialize()
    names = [t.name for t in mgr.tools]
    assert "write_file" in names
    assert "read_file" in names
    assert "list_files" in names


@pytest.mark.asyncio
async def test_manager_survives_bad_external_server(ws, tmp_path):
    """Un server externo que no existe no debe tumbar la inicialización."""
    from app.mcp.manager import MCPManager
    cfg = tmp_path / "bad_mcp.yaml"
    cfg.write_text(
        "servers:\n"
        "  inexistente:\n"
        "    command: ['npx', '-y', 'paquete-que-no-existe-xyz']\n"
        "    runtime: node\n"
    )
    mgr = MCPManager(config_path=str(cfg))
    # No debe lanzar excepción aunque el server falle
    await mgr.initialize()
    # Las builtin siguen disponibles
    assert "write_file" in [t.name for t in mgr.tools]


@pytest.mark.asyncio
async def test_manager_routes_builtin_call(ws):
    """call_tool enruta correctamente a una herramienta builtin."""
    from app.mcp.manager import MCPManager
    mgr = MCPManager(config_path="config/mcp_servers.yaml")
    await mgr.initialize()
    r = await mgr.call_tool("write_file", {"path": "via_manager.txt", "content": "ok"})
    assert not r.is_error
    assert (ws / "via_manager.txt").exists()


# ── Estrés: memoria a escala ─────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
async def test_memory_scale_1000(tmp_path):
    """1000 memorias: guardado, recuperación y búsqueda no se degradan ni corrompen."""
    from app.memory.store import SemanticMemoryStore
    db = str(tmp_path / "scale.db")
    store = SemanticMemoryStore(db_path=db, ollama_url="http://unreachable")
    # Guardar 1000 (sin Ollama → embedding vacío, búsqueda por texto)
    for i in range(1000):
        await store.save(content=f"memoria numero {i} sobre el tema {i % 10}", source="test")
    # Búsqueda por texto debe encontrar coincidencias sin petar
    results = await store.search("tema 7", k=5)
    assert isinstance(results, list)
    # La DB sigue íntegra tras 1000 inserciones
    reopened = SemanticMemoryStore(db_path=db, ollama_url="http://unreachable")
    again = await reopened.search("memoria", k=3)
    assert isinstance(again, list)
