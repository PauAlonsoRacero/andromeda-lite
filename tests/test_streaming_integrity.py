"""Integridad del camino streaming, que ahora usan navegador Y escritorio."""
import asyncio
import logging
import types

logging.disable(logging.CRITICAL)


def _spec():
    from app.specialists.registry import SpecialistRegistry
    reg = SpecialistRegistry("config/specialists.yaml")
    reg.set_available_models(["qwen3:14b"])
    return [s for s in reg.get_all() if s.model_name][:1]


def _run_stream(prompt, config):
    from app.core.streaming import staircase_stream

    async def main():
        trozos, final = [], None
        async for ch in staircase_stream(_spec(), prompt, config, "r1"):
            if ch.get("is_final"):
                final = ch
            elif ch.get("content"):
                trozos.append(ch["content"])
        return trozos, final
    return asyncio.run(main())


def _fake_tools(monkeypatch, texto="La hora en Madrid son las 14:05."):
    import app.core.model_catalog as mc
    import app.mcp.executor as mx

    async def stream_with_tools(self, *, on_token, **kw):
        for trozo in texto.split(" "):
            await on_token(trozo + " ")
        return texto, [{"tool": "get_current_time"}]
    monkeypatch.setattr(mx.MCPExecutor, "stream_with_tools", stream_with_tools)
    monkeypatch.setattr(mc, "supports_tools", lambda m: True)
    # Herramienta con nombre y descripción reales: ahora pasan por el selector
    # de relevancia, que descarta las que no tienen que ver con el mensaje.
    herramienta = types.SimpleNamespace(name="get_current_time",
                                        description="Get the current time in a timezone",
                                        server_id="time")
    return types.SimpleNamespace(tools=[herramienta], has_external_tools=True)


def test_stream_finishes_without_error(monkeypatch):
    """El bug: merge_responses de Lite no aceptaba los parámetros que le pasa el
    código compartido con Pro, y lanzaba al final de CADA respuesta. El texto
    se veía, pero la respuesta acababa en error: sin metadatos, sin id, sin
    votos. Este test recorre el stream hasta el final."""
    mcp = _fake_tools(monkeypatch)
    trozos, final = _run_stream("qué hora es", {"ollama_url": "http://127.0.0.1:1",
                                                "mcp_manager": mcp, "timeout": 5})
    assert final is not None, "el stream no emitió un final"
    assert not final.get("metadata", {}).get("error"), "el stream terminó en error"


def test_mcp_tools_work_in_streaming(monkeypatch):
    """En el navegador las herramientas MCP no funcionaban nunca; ahora el
    escritorio también va por aquí, así que perderlas sería una regresión."""
    mcp = _fake_tools(monkeypatch)
    trozos, _ = _run_stream("qué hora es", {"ollama_url": "http://127.0.0.1:1",
                                            "mcp_manager": mcp, "timeout": 5})
    assert "".join(trozos).strip() == "La hora en Madrid son las 14:05."
    assert len(trozos) > 1, "se emitió de golpe en vez de a trozos"


def test_lite_stubs_accept_pro_arguments():
    """Los esqueletos de Lite deben tolerar parámetros que solo usa Pro."""
    from app.core.classifier import classify_prompt
    from app.core.merger import merge_responses
    r = asyncio.run(merge_responses(
        [{"success": True, "content": "hola"}], skip_interpret=True, algo_nuevo=1))
    assert r == "hola"
    asyncio.run(classify_prompt("x", [], parametro_de_pro=True))


def test_no_mcp_tools_in_incognito():
    """Incógnito promete no salir a internet; una herramienta fetch lo haría."""
    import inspect
    from app.core import router
    from app.routes import chat
    src_chat, src_router = inspect.getsource(chat), inspect.getsource(router)
    assert '"mcp_manager": (None if (chat_request.incognito' in src_chat
    assert '"mcp_manager": (None if request.incognito' in src_router


def test_irrelevant_tools_are_not_offered(monkeypatch):
    """Con herramientas conectadas pero ninguna relevante, no hay bucle: la
    respuesta va directa. Antes cada mensaje inyectaba las 52 herramientas."""
    import app.core.model_catalog as mc
    import app.mcp.executor as mx
    llamado = []

    async def stream_with_tools(self, **kw):
        llamado.append(True)
        return "", []
    monkeypatch.setattr(mx.MCPExecutor, "stream_with_tools", stream_with_tools)
    monkeypatch.setattr(mc, "supports_tools", lambda m: True)
    mcp = types.SimpleNamespace(tools=[types.SimpleNamespace(
        name="get_current_time", description="Get the current time", server_id="time")],
        has_external_tools=True)
    _run_stream("explícame los punteros en C",
                {"ollama_url": "http://127.0.0.1:1", "mcp_manager": mcp, "timeout": 2})
    assert not llamado, "entró en el bucle de herramientas sin ninguna relevante"
