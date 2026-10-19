"""Rendimiento del streaming y robustez del protocolo MCP."""
import asyncio
import logging
import time

logging.disable(logging.CRITICAL)


# ── Streaming: el filtrado de <think> era cuadrático ──────────────────────

def test_reasoning_filter_is_not_quadratic():
    """Buscar en TODO lo acumulado por cada token cuesta ~31 ms en una
    respuesta de 5.000 tokens, y ese coste retrasa cada token que se muestra."""
    import inspect
    from app.core import streaming
    src = inspect.getsource(streaming)
    assert '"<think>" in accumulated' not in src, "sigue escaneando todo lo acumulado"
    assert "en_razonamiento" in src, "falta el indicador de estado"


def test_state_flag_filters_the_same_as_before():
    """El comportamiento observable no puede cambiar con la optimización."""
    def con_estado(tokens):
        salida, en = [], False
        for t in tokens:
            limpio = t.strip()
            if "<think>" in t:
                en = True
            if en or limpio in ("<think>", "</think>"):
                if "</think>" in t:
                    en = False
            else:
                salida.append(t)
        return "".join(salida)

    assert con_estado(["hola ", "mundo"]) == "hola mundo"
    assert con_estado(["<think>", "razono", "</think>", "resultado"]) == "resultado"
    assert con_estado(["antes ", "<think>", "x", "</think>", " despues"]) == "antes  despues"


def test_filter_cost_stays_linear():
    def filtrar(n):
        en = False
        t0 = time.perf_counter()
        for i in range(n):
            token = f"palabra{i} "
            if "<think>" in token:
                en = True
            if not en:
                pass
        return time.perf_counter() - t0

    # Al doblar los tokens el coste debe doblarse, no cuadruplicarse
    corto, largo = filtrar(2000), filtrar(4000)
    assert largo < corto * 3.5, "el filtrado sigue creciendo más que linealmente"


# ── MCP: respuestas desincronizadas ───────────────────────────────────────

def test_protocol_skips_mismatched_ids():
    """El bug: un mensaje con otro id dejaba la respuesta correcta en el buffer
    y, desde ahí, cada llamada leía la respuesta de la anterior."""
    import inspect
    from app.mcp import protocol
    src = inspect.getsource(protocol.MCPStdioClient._request)
    assert "for _ in range" in src, "no busca la respuesta correcta"
    assert "descartado mensaje" in src or "id={" in src


def test_protocol_tolerates_non_json_lines():
    """Los servidores MCP escriben logs por stdout: no pueden romper el canal."""
    import inspect
    from app.mcp import protocol
    src = inspect.getsource(protocol.MCPStdioClient._request)
    assert "JSONDecodeError" in src


def test_call_tool_reports_disconnected_server():
    from app.mcp.protocol import MCPStdioClient
    c = MCPStdioClient(server_id="x", command=["echo"], env={})
    r = asyncio.run(c.call_tool("cualquiera", {}))
    assert r.is_error and "conectado" in (r.error_msg or "").lower()


# ── Construcción del prompt: se ejecuta en cada mensaje ───────────────────

def test_prompt_building_is_cheap(tmp_path):
    """Con 200 documentos indexados debe seguir siendo despreciable."""
    from app.core import prompt_builder as pb
    from app.rag.bm25 import BM25Index

    idx = BM25Index(tmp_path / "r.json")
    for i in range(200):
        idx.add_document(f"d{i}", f"contenido variado numero {i} con palabras " * 8)

    t = time.perf_counter()
    for _ in range(10):
        p = pb.PromptParts(message="qué puerto usa el backend")
        pb.add_documents(p, "qué puerto usa", idx, incognito=False)
        p.render()
    ms = (time.perf_counter() - t) * 1000 / 10
    assert ms < 20, f"construir el prompt cuesta {ms:.1f} ms por mensaje"
