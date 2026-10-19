"""Parámetros de inferencia ajustados al hardware y prompt de sistema mínimo."""
import logging

logging.disable(logging.CRITICAL)


# ── Ajuste por hardware ────────────────────────────────────────────────────

def test_context_scales_with_memory():
    """Ollama usa 4096 por defecto porque no sabe en qué máquina corre."""
    from app.core.inference_tuning import context_window
    assert context_window(32) > context_window(8)
    assert context_window(4) == 4096          # equipos modestos, sin arriesgar


def test_gpu_layers_forced_only_with_enough_vram():
    """Si Ollama estima a la baja, el modelo corre en CPU y la velocidad cae."""
    from app.core.inference_tuning import gpu_layers
    assert gpu_layers(16, "cuda") == 999      # todas las capas a la GPU
    assert gpu_layers(4, "cuda") is None      # poca VRAM: que estime Ollama


def test_apple_silicon_is_left_alone():
    """Memoria unificada: Metal reparte mejor que una heurística nuestra."""
    from app.core.inference_tuning import gpu_layers
    assert gpu_layers(0, "metal") is None
    assert gpu_layers(48, "apple") is None


def test_threads_leave_headroom():
    """Usar todos los núcleos provoca throttling y acaba generando MENOS."""
    from app.core.inference_tuning import cpu_threads
    assert cpu_threads(12) == 11
    assert cpu_threads(2) is None             # equipos modestos: que decida Ollama


def test_explicit_options_are_never_overridden():
    """Lo que pide quien llama manda: son decisiones explícitas."""
    from app.core.inference_tuning import build_options
    o = build_options({"temperature": 0.1, "num_ctx": 2048},
                      vram_gb=24, cpu_cores=16, acceleration="cuda")
    assert o["temperature"] == 0.1
    assert o["num_ctx"] == 2048               # no lo pisa el ajuste automático


def test_env_overrides_work(monkeypatch):
    from app.core.inference_tuning import context_window, cpu_threads
    monkeypatch.setenv("ANDROMEDA_NUM_CTX", "32768")
    assert context_window(4) == 32768
    monkeypatch.setenv("ANDROMEDA_NUM_THREAD", "6")
    assert cpu_threads(16) == 6


def test_tuning_degrades_without_hardware():
    """Sin datos del equipo no puede romper nada."""
    from app.core.streaming import _tuned_options
    base = {"temperature": 0.7}
    assert _tuned_options(base, None) == base
    assert _tuned_options(base, {}) == base


def test_both_paths_apply_tuning():
    import inspect
    from app.core import executor, streaming
    for mod in (streaming, executor):
        assert "_tuned_options" in inspect.getsource(mod)


# ── Prompt de sistema: no gastar contexto de más ──────────────────────────

def test_file_instructions_omitted_when_not_needed():
    """~420 tokens de instrucciones de archivo se enviaban en CADA mensaje,
    aunque solo se preguntara la hora. En una ventana de 4.096 eso es más del
    10% del contexto, y diluye la atención sobre lo preguntado."""
    from app.specialists.identity import with_identity
    corto = with_identity("Eres útil.", "generalist", "gemma3:27b",
                          user_prompt="qué día es hoy")
    largo = with_identity("Eres útil.", "generalist", "gemma3:27b",
                          user_prompt="crea un archivo index.html")
    # Las instrucciones de archivos (~1.500 caracteres) solo van cuando hacen falta.
    assert len(largo) - len(corto) > 1000
    assert "andromeda:write" not in corto
    assert "andromeda:write" in largo


def test_file_hints_cover_both_languages():
    from app.specialists.identity import needs_file_tools
    for p in ("crea un archivo", "modifica el script", "save this document",
              "edita el html", "genera un pdf"):
        assert needs_file_tools(p), p
    for p in ("qué día es hoy", "explícame la recursividad", "cuánto es 2+2"):
        assert not needs_file_tools(p), p


def test_ambiguity_keeps_the_instructions():
    """Quedarse sin ellas cuando hacen falta rompe la funcionalidad; incluirlas
    de más solo cuesta contexto. Ante la duda, incluirlas."""
    from app.specialists.identity import needs_file_tools
    assert needs_file_tools("") is True


def test_date_is_always_present():
    """La optimización no puede llevarse por delante la fecha."""
    from datetime import datetime
    from app.specialists.identity import with_identity
    out = with_identity("x", "generalist", "gemma3:27b", user_prompt="hola")
    assert str(datetime.now().year) in out[:300]


# ── Prefill: tamaño de lote ────────────────────────────────────────────────

def test_batch_size_scales_with_vram():
    """El lote de prefill afecta a cuánto tarda el modelo en 'leer' el prompt,
    que es justo la espera que percibe el usuario antes de la primera palabra."""
    from app.core.inference_tuning import batch_size
    assert batch_size(24, "cuda") == 2048
    assert batch_size(12, "cuda") == 1024
    assert batch_size(6, "cuda") is None       # poca VRAM: el valor de Ollama


def test_batch_size_ignored_without_gpu():
    """Sin GPU los lotes grandes no aportan nada y gastan memoria."""
    from app.core.inference_tuning import batch_size
    assert batch_size(0, "cpu") is None


def test_batch_size_env_override(monkeypatch):
    from app.core.inference_tuning import batch_size
    monkeypatch.setenv("ANDROMEDA_NUM_BATCH", "4096")
    assert batch_size(0, "cpu") == 4096


# ── Recomendaciones para el servidor de Ollama ────────────────────────────

def test_flash_attention_recommended_on_cuda():
    """El propio equipo de Ollama lo recomienda para maximizar el rendimiento."""
    from app.core.inference_tuning import recommended_server_env
    assert recommended_server_env(16, "cuda").get("OLLAMA_FLASH_ATTENTION") == "1"


def test_kv_cache_quantization_only_when_vram_is_tight():
    """Cuantizar la caché permite ~2x de contexto, pero la caché es más
    sensible a la cuantización que los pesos: solo cuando compensa."""
    from app.core.inference_tuning import recommended_server_env
    assert "OLLAMA_KV_CACHE_TYPE" in recommended_server_env(8, "cuda")
    assert "OLLAMA_KV_CACHE_TYPE" not in recommended_server_env(24, "cuda")


def test_kv_cache_uses_q8_not_q4():
    """A 4 bits la calidad se resiente en contextos largos."""
    from app.core.inference_tuning import recommended_server_env
    assert recommended_server_env(8, "cuda")["OLLAMA_KV_CACHE_TYPE"] == "q8_0"


def test_no_recommendations_on_apple_silicon():
    """Flash Attention es de CUDA/ROCm; en Metal no aplica."""
    from app.core.inference_tuning import recommended_server_env
    assert recommended_server_env(0, "metal") == {}


def test_panel_surfaces_missing_server_vars():
    """Andromeda no puede fijarlas (son del proceso `ollama serve`), pero sí
    detectar que faltan y decírselo al usuario."""
    import inspect
    from app.routes import components_health
    src = inspect.getsource(components_health)
    assert "recommended_server_env" in src
    assert "cd.ollama_tune" in src
