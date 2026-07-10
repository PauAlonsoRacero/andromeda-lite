"""
Catálogo de modelos de Ollama + clasificación en tiers por requisitos reales.

Los tiers se basan en CUÁNTA VRAM hace falta para correr el modelo cómodamente,
y se asocian a GPUs de referencia concretas (NVIDIA / AMD / Intel, sobremesa y portátil).
La velocidad (tokens/s) se ESTIMA a partir del ancho de banda de memoria de la GPU
y el tamaño del modelo en memoria — es una estimación, no una medida real.
"""
from __future__ import annotations


# ── Tiers por VRAM necesaria ────────────────────────────────────────────────
# La VRAM es el factor que decide si un modelo CORRE o no. Por eso es la base.
#   T1: hasta ~6 GB VRAM   → entra en cualquier GPU moderna, incluso portátiles
#   T2: ~6-12 GB VRAM      → GPU de gama media (RTX 3060 8GB, 4060, etc.)
#   T3: ~12-24 GB VRAM     → GPU buena (RTX 4070 Ti / 5070 Ti 16GB, 3090, 4090)
#   T4: 24+ GB VRAM        → GPU tope o multi-GPU (A6000, 2x4090, etc.)
TIER_VRAM_LIMITS = {1: 6.0, 2: 12.0, 3: 24.0}  # T4 = lo que pase de 24

TIER_INFO = {
    1: {
        "name": "T1 · Ligero",
        "vram_range": "hasta 6 GB",
        "desc": "Corre en casi cualquier GPU moderna, incluso portátiles modestos.",
        "gpus_desktop": ["RTX 3050 8GB", "RTX 3060 8GB", "RTX 4060", "RX 6600 8GB", "Arc A750 8GB"],
        "gpus_laptop": ["RTX 3050 Ti Laptop", "RTX 4050 Laptop 6GB", "RTX 4060 Laptop 8GB"],
    },
    2: {
        "name": "T2 · Medio",
        "vram_range": "6 – 12 GB",
        "desc": "GPU de gama media. Equilibrio entre calidad y recursos.",
        "gpus_desktop": ["RTX 3060 12GB", "RTX 4060 Ti 8/16GB", "RTX 5060 Ti", "RX 6700 XT 12GB", "RX 7700 XT"],
        "gpus_laptop": ["RTX 4070 Laptop 8GB", "RTX 4080 Laptop 12GB", "RTX 5070 Laptop"],
    },
    3: {
        "name": "T3 · Potente",
        "vram_range": "12 – 24 GB",
        "desc": "GPU buena. Para modelos grandes con calidad alta.",
        "gpus_desktop": ["RTX 4070 Ti Super 16GB", "RTX 5070 Ti 16GB", "RTX 3090 24GB", "RTX 4090 24GB", "RX 7900 XTX 24GB"],
        "gpus_laptop": ["RTX 4090 Laptop 16GB", "RTX 5090 Laptop 24GB"],
    },
    4: {
        "name": "T4 · Enorme",
        "vram_range": "24+ GB",
        "desc": "GPU tope de gama o varias GPUs. Modelos enormes, máxima calidad.",
        "gpus_desktop": ["RTX 5090 32GB", "RTX A6000 48GB", "2x RTX 4090", "AMD MI300"],
        "gpus_laptop": ["No recomendado en portátil — requiere sobremesa o servidor"],
    },
}


def estimate_vram(params_b: float, quant: str = "Q4") -> float:
    """
    Estima la VRAM (GB) necesaria para correr el modelo.
    Incluye los pesos + overhead de KV cache y contexto.
    """
    # GB por cada billón de parámetros según cuantización
    factor = {"Q4": 0.65, "Q5": 0.75, "Q8": 1.1, "F16": 2.0}.get(quant, 0.65)
    weights = params_b * factor
    # Overhead: KV cache + activaciones + contexto (~20% o mínimo 0.8GB)
    overhead = max(weights * 0.2, 0.8)
    return round(weights + overhead, 1)


def classify_tier(params_b: float, vram_gb: float = 0) -> int:
    """
    Encasilla el modelo en T1-T4 según la VRAM que necesita para correr.
    Si no se pasa vram, se estima a partir de los parámetros.
    """
    if vram_gb <= 0:
        vram_gb = estimate_vram(params_b)
    if vram_gb <= TIER_VRAM_LIMITS[1]: return 1
    if vram_gb <= TIER_VRAM_LIMITS[2]: return 2
    if vram_gb <= TIER_VRAM_LIMITS[3]: return 3
    return 4


# ── Ancho de banda de memoria de GPUs comunes (GB/s) ────────────────────────
# La velocidad de inferencia (tokens/s) depende sobre todo del ancho de banda,
# porque generar cada token requiere leer todos los pesos del modelo de memoria.
GPU_BANDWIDTH = {
    # NVIDIA sobremesa
    "rtx 3050": 224, "rtx 3060": 360, "rtx 3060 ti": 448, "rtx 3070": 448,
    "rtx 3080": 760, "rtx 3090": 936,
    "rtx 4060": 272, "rtx 4060 ti": 288, "rtx 4070": 504, "rtx 4070 ti": 504,
    "rtx 4070 ti super": 672, "rtx 4080": 717, "rtx 4090": 1008,
    "rtx 5060": 448, "rtx 5070": 672, "rtx 5070 ti": 896, "rtx 5080": 960, "rtx 5090": 1792,
    # NVIDIA portátil (menor ancho de banda que sobremesa)
    "rtx 4050 laptop": 192, "rtx 4060 laptop": 256, "rtx 4070 laptop": 256,
    "rtx 4080 laptop": 432, "rtx 4090 laptop": 576, "rtx 5070 laptop": 384,
    # AMD
    "rx 6600": 224, "rx 6700 xt": 384, "rx 6800": 512, "rx 6900 xt": 512,
    "rx 7700 xt": 432, "rx 7800 xt": 624, "rx 7900 xtx": 960,
    # Intel
    "arc a750": 512, "arc a770": 560, "arc b580": 456,
    # Apple Silicon (memoria unificada)
    "m1": 68, "m1 pro": 200, "m1 max": 400, "m2": 100, "m2 pro": 200,
    "m2 max": 400, "m3": 100, "m3 pro": 150, "m3 max": 400, "m4": 120, "m4 max": 546,
}


def estimate_tokens_per_sec(params_b: float, bandwidth_gbs: float, quant: str = "Q4") -> float:
    """
    Estima tokens/s = ancho_de_banda / tamaño_del_modelo_en_memoria.
    Es la fórmula estándar (memory-bound). Aplica ~70% de eficiencia real.
    """
    if params_b <= 0 or bandwidth_gbs <= 0:
        return 0
    factor = {"Q4": 0.65, "Q5": 0.75, "Q8": 1.1, "F16": 2.0}.get(quant, 0.65)
    model_size_gb = params_b * factor
    if model_size_gb <= 0:
        return 0
    theoretical = bandwidth_gbs / model_size_gb
    return round(theoretical * 0.7, 1)  # 70% eficiencia real


def lookup_bandwidth(gpu_name: str) -> float:
    """Busca el ancho de banda de una GPU por nombre (fuzzy)."""
    if not gpu_name:
        return 0
    n = gpu_name.lower().strip()
    # Match exacto primero
    if n in GPU_BANDWIDTH:
        return GPU_BANDWIDTH[n]
    # Match parcial (el nombre detectado suele tener texto extra)
    best = 0
    best_len = 0
    for key, bw in GPU_BANDWIDTH.items():
        if key in n and len(key) > best_len:
            best = bw
            best_len = len(key)
    return best


# ── Catálogo curado de modelos ──────────────────────────────────────────────
CATALOG = [
    # ── Generación reciente ──────────────────────────────────────────────────
    {
        "name": "qwen3:8b", "family": "Qwen 3", "params_b": 8,
        "description": "Qwen generation 3 with switchable reasoning mode. Very versatile.",
        "uses": ["Chat general", "Razonamiento", "Código"], "tags": ["general", "reasoning"],
        "context": 40960, "license": "Apache 2.0",
    },
    {
        "name": "qwen3:14b", "family": "Qwen 3", "params_b": 14,
        "description": "Mid-size Qwen 3. Solid reasoning while keeping good speed.",
        "uses": ["Razonamiento", "Análisis", "Código"], "tags": ["general", "reasoning"],
        "context": 40960, "license": "Apache 2.0",
    },
    {
        "name": "qwen3:32b", "family": "Qwen 3", "params_b": 32,
        "description": "Large Qwen 3. Top local quality for those with VRAM to spare.",
        "uses": ["Tareas complejas", "Razonamiento profundo"], "tags": ["general", "reasoning"],
        "context": 40960, "license": "Apache 2.0",
    },
    {
        "name": "gemma3:4b", "family": "Gemma 3", "params_b": 4,
        "description": "Compact Gemma 3 by Google. Multimodal (understands images) and fast.",
        "uses": ["Chat general", "Visión", "Tareas rápidas"], "tags": ["general", "vision"],
        "context": 131072, "license": "Gemma",
    },
    {
        "name": "gemma3:12b", "family": "Gemma 3", "params_b": 12,
        "description": "Mid-size Gemma 3. Multimodal with very good text quality.",
        "uses": ["Chat general", "Visión", "Redacción"], "tags": ["general", "vision"],
        "context": 131072, "license": "Gemma",
    },
    {
        "name": "gemma3:27b", "family": "Gemma 3", "params_b": 27,
        "description": "Large Gemma 3. Among Google's best open models, multimodal.",
        "uses": ["Tareas complejas", "Visión", "Análisis"], "tags": ["general", "vision"],
        "context": 131072, "license": "Gemma",
    },
    {
        "name": "deepseek-r1:32b", "family": "DeepSeek R1", "params_b": 32,
        "description": "Large R1 reasoner. Long chains of thought for hard problems.",
        "uses": ["Matemáticas", "Lógica", "Planificación"], "tags": ["reasoning"],
        "context": 131072, "license": "MIT",
    },
    {
        "name": "phi4:14b", "family": "Phi 4", "params_b": 14,
        "description": "Microsoft's Phi 4. Surprising reasoning and math for its size.",
        "uses": ["Razonamiento", "Matemáticas", "Código"], "tags": ["general", "reasoning"],
        "context": 16384, "license": "MIT",
    },
    {
        "name": "llava:7b", "family": "LLaVA", "params_b": 7,
        "description": "Classic vision model: describes images, reads screenshots, analyzes photos.",
        "uses": ["Visión", "Describir imágenes", "OCR ligero"], "tags": ["vision"],
        "context": 4096, "license": "Apache 2.0",
    },
    {
        "name": "llama3.2-vision:11b", "family": "Llama 3.2 Vision", "params_b": 11,
        "description": "Meta's Llama with vision. Understands images, charts and documents.",
        "uses": ["Visión", "Documentos", "Gráficos"], "tags": ["vision"],
        "context": 131072, "license": "Llama 3.2",
    },
    {
        "name": "codellama:7b", "family": "Code Llama", "params_b": 7,
        "description": "Meta's code specialist. Reliable veteran for completion and FIM.",
        "uses": ["Código", "Autocompletado"], "tags": ["coding"],
        "context": 16384, "license": "Llama 2",
    },
    {
        "name": "codegemma:7b", "family": "CodeGemma", "params_b": 7,
        "description": "Google's Gemma-based coder. Good at Python and infrastructure.",
        "uses": ["Código", "Scripts", "DevOps"], "tags": ["coding"],
        "context": 8192, "license": "Gemma",
    },
    {
        "name": "smollm2:1.7b", "family": "SmolLM 2", "params_b": 1.7,
        "description": "Tiny but capable. For very limited hardware or instant replies.",
        "uses": ["Tareas simples", "Hardware limitado"], "tags": ["general"],
        "context": 8192, "license": "Apache 2.0",
    },
    {
        "name": "mistral-nemo:12b", "family": "Mistral Nemo", "params_b": 12,
        "description": "Mistral×NVIDIA collaboration. Excellent multilingual, large context.",
        "uses": ["Multilingüe", "Chat general", "Redacción"], "tags": ["general"],
        "context": 131072, "license": "Apache 2.0",
    },
    {
        "name": "qwen2.5-coder:7b", "family": "Qwen2.5 Coder", "params_b": 7,
        "description": "Alibaba's code model, excellent for programming and debugging.",
        "uses": ["Código", "Debugging", "Refactor"], "tags": ["coding"],
        "context": 32768, "license": "Apache 2.0",
    },
    {
        "name": "qwen2.5-coder:14b", "family": "Qwen2.5 Coder", "params_b": 14,
        "description": "Mid-size Qwen coder. Good quality/resource balance.",
        "uses": ["Código", "Arquitectura", "Code review"], "tags": ["coding"],
        "context": 32768, "license": "Apache 2.0",
    },
    {
        "name": "qwen2.5-coder:32b", "family": "Qwen2.5 Coder", "params_b": 32,
        "description": "Large Qwen coder. For complex systems and critical code.",
        "uses": ["Sistemas complejos", "Código crítico"], "tags": ["coding"],
        "context": 32768, "license": "Apache 2.0",
    },
    {
        "name": "llama3.2:3b", "family": "Llama 3.2", "params_b": 3,
        "description": "Lightweight Meta model. Fast, ideal for simple general tasks.",
        "uses": ["Chat general", "Resúmenes", "Tareas rápidas"], "tags": ["general"],
        "context": 131072, "license": "Llama 3.2",
    },
    {
        "name": "llama3.1:8b", "family": "Llama 3.1", "params_b": 8,
        "description": "Versatile Meta model. A good generalist for most tasks.",
        "uses": ["Chat general", "Análisis", "Escritura"], "tags": ["general"],
        "context": 131072, "license": "Llama 3.1",
    },
    {
        "name": "llama3.3:70b", "family": "Llama 3.3", "params_b": 70,
        "description": "Meta's large model. Near GPT-4 quality on many tasks.",
        "uses": ["Razonamiento", "Tareas complejas", "Máxima calidad"], "tags": ["general"],
        "context": 131072, "license": "Llama 3.3",
    },
    {
        "name": "mistral:7b", "family": "Mistral", "params_b": 7,
        "description": "Efficient model from Mistral AI. Fast and capable.",
        "uses": ["Chat general", "Instrucciones"], "tags": ["general"],
        "context": 32768, "license": "Apache 2.0",
    },
    {
        "name": "mixtral:8x7b", "family": "Mixtral MoE", "params_b": 47,
        "description": "Mistral mixture-of-experts. Powerful, uses only part of its weights per token.",
        "uses": ["Razonamiento", "Multilingüe", "Tareas complejas"], "tags": ["general"],
        "context": 32768, "license": "Apache 2.0",
    },
    {
        "name": "phi3.5:3.8b", "family": "Phi 3.5", "params_b": 3.8,
        "description": "Small Microsoft model with surprising reasoning for its size.",
        "uses": ["Razonamiento", "Tareas rápidas", "Edge"], "tags": ["general", "reasoning"],
        "context": 131072, "license": "MIT",
    },
    {
        "name": "gemma2:9b", "family": "Gemma 2", "params_b": 9,
        "description": "Open Google model. Good general and multilingual performance.",
        "uses": ["Chat general", "Multilingüe"], "tags": ["general"],
        "context": 8192, "license": "Gemma",
    },
    {
        "name": "gemma2:27b", "family": "Gemma 2", "params_b": 27,
        "description": "Large Gemma. High quality for demanding tasks.",
        "uses": ["Análisis", "Escritura avanzada"], "tags": ["general"],
        "context": 8192, "license": "Gemma",
    },
    {
        "name": "deepseek-coder-v2:16b", "family": "DeepSeek Coder V2", "params_b": 16,
        "description": "DeepSeek MoE coder. Excellent at code, very efficient.",
        "uses": ["Código", "Algoritmos"], "tags": ["coding"],
        "context": 131072, "license": "DeepSeek",
    },
    {
        "name": "deepseek-r1:7b", "family": "DeepSeek R1", "params_b": 7,
        "description": "Reasoning model with chain of thought. Thinks before answering.",
        "uses": ["Razonamiento", "Matemáticas", "Lógica"], "tags": ["reasoning"],
        "context": 131072, "license": "MIT",
    },
    {
        "name": "deepseek-r1:14b", "family": "DeepSeek R1", "params_b": 14,
        "description": "Advanced chain-of-thought reasoning. More capable than the 7b.",
        "uses": ["Razonamiento", "Matemáticas", "Problemas complejos"], "tags": ["reasoning"],
        "context": 131072, "license": "MIT",
    },
    {
        "name": "nomic-embed-text", "family": "Nomic Embed", "params_b": 0.137,
        "description": "Embeddings model for semantic search and RAG.",
        "uses": ["Embeddings", "RAG", "Búsqueda"], "tags": ["embedding"],
        "context": 8192, "license": "Apache 2.0",
    },
]



# ── Capacidad de herramientas (tool-calling: crear archivos, MCP, etc.) ──────
# Andromeda usa un protocolo de herramientas basado en prompt, así que la
# capacidad real depende de lo bien que el modelo siga instrucciones de formato.
# Marcamos como capaces las familias modernas con buen seguimiento de
# instrucciones, y excluimos modelos viejos/diminutos/especializados que fallan
# (p. ej. llama2) o que no son de chat (embeddings, visión pura).
_TOOL_CAPABLE = (
    "qwen2.5", "qwen3", "qwen2", "qwq",          # Qwen modernos
    "llama3.1", "llama3.2", "llama3.3", "llama-3.1", "llama-3.2", "llama-3.3",
    "mistral", "mixtral", "ministral", "mathstral",  # Mistral (0.3+)
    "command-r", "command-a",
    "hermes3", "nous-hermes2", "firefunction",
    "granite3", "granite-3", "nemotron",
    "deepseek-coder-v2", "deepseek-v2", "deepseek-v3", "deepseek-r1",
    "phi4", "phi-4", "smollm2", "codestral",
)
# Nunca capaces (aunque el nombre contenga un prefijo de arriba).
_TOOL_INCAPABLE = (
    "embed", "embedding", "bge", "nomic", "minilm", "e5-",  # embeddings
    "llava", "bakllava", "moondream",                       # visión pura
    "llama2", "llama-2", "codellama", "tinyllama", "tinydolphin",
    "orca-mini", "vicuna", "alpaca", "stablelm2:1", "gemma:2b", "phi:",
)


def supports_tools(model_name: str) -> bool:
    """True si el modelo es fiable usando herramientas (crear archivos, MCP)."""
    if not model_name:
        return False
    n = model_name.lower()
    if any(bad in n for bad in _TOOL_INCAPABLE):
        return False
    if any(good in n for good in _TOOL_CAPABLE):
        return True
    # Heurística por tamaño para familias no listadas: <3B suele fallar salvo coders.
    try:
        import re as _re
        mb = _re.search(r"(\d+(?:\.\d+)?)\s*b", n)
        if mb and float(mb.group(1)) < 3 and "coder" not in n and "code" not in n:
            return False
    except Exception:
        pass
    # Por defecto, los modelos modernos de chat se consideran capaces.
    return True


def enrich_model(m: dict, quant: str = "Q4", user_bandwidth: float = 0, user_vram: float = 0) -> dict:
    """Añade a un modelo: VRAM, tier, GPUs de referencia, velocidad estimada y si cabe en tu GPU."""
    vram = estimate_vram(m["params_b"], quant)
    tier = classify_tier(m["params_b"], vram)
    info = TIER_INFO[tier]

    enriched = {
        **m,
        "vram_estimated_gb": vram,
        "tier": tier,
        "tier_name": info["name"],
        "tier_vram_range": info["vram_range"],
        "tier_desc": info["desc"],
        "supports_tools": supports_tools(m["name"]),
        "gpus_desktop": info["gpus_desktop"],
        "gpus_laptop": info["gpus_laptop"],
    }

    # Velocidad estimada según el hardware del usuario (si lo conocemos)
    if user_bandwidth > 0:
        tps = estimate_tokens_per_sec(m["params_b"], user_bandwidth, quant)
        enriched["est_tokens_per_sec"] = tps
        # Clasificar la experiencia
        if tps >= 40: enriched["speed_label"] = "Muy rápido"
        elif tps >= 20: enriched["speed_label"] = "Rápido"
        elif tps >= 10: enriched["speed_label"] = "Usable"
        elif tps > 0: enriched["speed_label"] = "Lento"
        else: enriched["speed_label"] = "—"

    # ¿Es apto para la VRAM del usuario? Con margen de seguridad.
    # El SO, el escritorio y otras apps ya consumen algo de VRAM, así que
    # reservamos un colchón antes de declarar un modelo "apto".
    if user_vram > 0:
        SAFETY_MARGIN_GB = 1.5  # colchón para SO + otras apps
        usable_vram = user_vram - SAFETY_MARGIN_GB
        headroom = round(usable_vram - vram, 1)
        enriched["vram_headroom_gb"] = headroom
        enriched["safety_margin_gb"] = SAFETY_MARGIN_GB

        if vram <= usable_vram - 1.5:
            enriched["fits_status"] = "apto"          # holgado
        elif vram <= usable_vram:
            enriched["fits_status"] = "apto_justo"    # entra pero al límite
        else:
            enriched["fits_status"] = "no_apto"
        # Compat: booleano simple
        enriched["fits_in_vram"] = enriched["fits_status"] != "no_apto"

    return enriched


def get_catalog(query: str = "", quant: str = "Q4",
                user_bandwidth: float = 0, user_vram: float = 0) -> list[dict]:
    """Devuelve el catálogo filtrado y enriquecido con datos del hardware del usuario."""
    q = query.lower().strip()
    result = []
    for m in CATALOG:
        if q and q not in m["name"].lower() and q not in m["family"].lower() \
           and not any(q in t for t in m["tags"]) and not any(q in u.lower() for u in m["uses"]):
            continue
        result.append(enrich_model(m, quant, user_bandwidth, user_vram))
    return result
