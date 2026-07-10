"""
schemas.py — Contratos de datos de Andromeda.

Todos los tipos que se intercambian entre capas del sistema están aquí.
Pydantic v2 valida automáticamente los tipos en los endpoints FastAPI.

Estructura:
  - ChatRequest     → lo que llega del usuario al POST /api/chat
  - ChatChunk       → un trozo de respuesta en streaming SSE
  - ChatResponse    → respuesta completa (modo no-streaming)
  - SpecialistProfile → perfil de un especialista en el catálogo
  - HardwareInfo    → resultado del detector de hardware
  - HardwarePolicy  → política derivada del hardware (cómo comportarse)
  - RuntimePolicy   → política aplicada a UN request concreto
  - TraceRecord     → registro completo de una petición (para observabilidad)
  - OrchestratorDecision → decisiones tomadas por el orquestador
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════════════════════
# MODELOS DE REQUEST / RESPONSE DEL CHAT
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# NIVELES DE MODELO POR ESPECIALISTA
# ══════════════════════════════════════════════════════════════════════════════

class ModelLevel(BaseModel):
    """
    Un nivel de potencia para un especialista.
    Cada especialista tiene 4 niveles: low, mid, high, ultra.
    El sistema elige automáticamente según la VRAM disponible.
    """
    name: str = Field(description="Nombre del nivel: low | mid | high | ultra")
    model_name: str = Field(description="Nombre exacto del modelo en Ollama")
    params_b: float = Field(description="Parámetros del modelo en billones (ej: 7.0 = 7B)")
    vram_required_gb: float = Field(description="VRAM mínima necesaria en GB")
    min_tier: int = Field(default=1, description="Tier mínimo de hardware requerido")
    description: str = Field(default="", description="Descripción del nivel")


class ModelTiers(BaseModel):
    """
    Catálogo de 4 niveles de potencia para un especialista.
    El sistema elige el nivel más alto que puede ejecutar según el hardware.
    El usuario puede sobreescribir la selección automática.
    """
    low:   ModelLevel | None = Field(default=None, description="6-9B — básico, T1+")
    mid:   ModelLevel | None = Field(default=None, description="13-17B — recomendado, T2+")
    high:  ModelLevel | None = Field(default=None, description="24-36B — alta calidad, T3+")
    ultra: ModelLevel | None = Field(default=None, description="60-70B — máxima calidad, T4")

    def best_for_tier(self, tier: int, vram_free_gb: float = 999.0) -> ModelLevel | None:
        """
        Retorna el mejor nivel disponible para el tier de hardware dado.
        Prioriza calidad — elige el más alto que puede ejecutarse.
        """
        candidates = []
        for level_name in ["ultra", "high", "mid", "low"]:
            level = getattr(self, level_name)
            if level and level.min_tier <= tier and level.vram_required_gb <= vram_free_gb:
                candidates.append(level)
        return candidates[0] if candidates else None

    def best_for_power(self, power_tier: int, hardware_tier: int,
                       vram_free_gb: float = 999.0) -> ModelLevel | None:
        """
        Núcleo de 'Andromeda Orquesta': elige el nivel adecuado a la POTENCIA
        que el prompt necesita, no el máximo que el hardware permite.

        power_tier (1-4) lo decide el orquestador según la complejidad:
          1 → low   (modelo más pequeño/rápido, p.ej. 3B)
          2 → mid   (7-8B)
          3 → high  (14B)
          4 → ultra (32B+)

        Se elige el nivel objetivo si cabe en el hardware y la VRAM; si no cabe,
        se baja al mejor que sí quepa. Nunca se sube por encima de lo pedido
        (eficiencia: no malgastar un 32B en un "hola").
        """
        order = ["low", "mid", "high", "ultra"]
        target_idx = max(0, min(power_tier - 1, 3))
        # De mayor a menor desde el objetivo: el objetivo primero, luego bajar.
        for idx in range(target_idx, -1, -1):
            level = getattr(self, order[idx])
            if level and level.min_tier <= hardware_tier and level.vram_required_gb <= vram_free_gb:
                return level
        # Si ni el low cabe, intentar lo que sea que quepa (degradación).
        return self.best_for_tier(hardware_tier, vram_free_gb)

    def level_for_name(self, name: str) -> ModelLevel | None:
        """Retorna el nivel por nombre (low/mid/high/ultra)."""
        return getattr(self, name, None)


class ChatRequest(BaseModel):
    """
    Cuerpo del POST /api/chat.
    Lo que el usuario (o la UI) envía al orquestador.
    """

    prompt: str = Field(
        ...,
        min_length=1,
        description="Texto de la pregunta o tarea del usuario",
    )
    strategy: str = Field(
        default="auto",
        description=(
            "Estrategia de ejecución. 'auto' = el clasificador decide. "
            "Opciones: single | iterative_refine | verifier_pass | "
            "confidence_weighted | hardware_aware_fallback | latency_first | quality_first"
        ),
    )
    specialists: list[str] = Field(
        default_factory=list,
        description=(
            "IDs de especialistas a forzar. Vacío = el clasificador decide. "
            "Ejemplo: ['software-engineering', 'verifier']"
        ),
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperatura de generación (0=determinista, 1=creativo)",
    )
    max_tokens: int = Field(
        default=2048,
        ge=64,
        le=32768,
        description="Número máximo de tokens a generar",
    )
    stream: bool = Field(
        default=True,
        description="Si True: respuesta por SSE token a token. Si False: JSON completo al final.",
    )
    incognito: bool = Field(
        default=False,
        description=(
            "Modo incógnito. Si True: 100% local, sin internet, sin guardar nada. "
            "Si False: puede buscar en internet para enriquecer respuestas."
        ),
    )
    web_search: bool = Field(
        default=True,
        description="Permitir búsqueda web (solo aplica si incognito=False).",
    )
    max_parallel: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description=(
            "Número máximo de IAs a usar en paralelo. "
            "None = el Policy Engine decide según hardware. "
            "1 = solo una IA (más rápido). 2-4 = más IAs (más calidad)."
        ),
    )
    specialist_levels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Override de nivel por especialista. "
            "Ejemplo: {'software-engineering': 'high', 'verifier': 'low'}. "
            "Si vacío, el sistema elige automáticamente según hardware."
        ),
    )
    force_model: str | None = Field(
        default=None,
        description=(
            "Fuerza un modelo concreto de Ollama para TODA la respuesta, "
            "saltándose el enrutamiento por tiers. Útil para probar un modelo "
            "recién descargado (p. ej. 'qwen3:32b'). Si está vacío, se usa el "
            "enrutamiento normal."
        ),
    )
    parallel_policy: str = Field(
        default="auto",
        description=(
            "Política de paralelismo: "
            "'auto' = el sistema decide, "
            "'max2' = máximo 2 IAs siempre (ahorra VRAM), "
            "'max1' = solo 1 IA (máxima velocidad), "
            "'max_hardware' = todas las que quepan en el hardware."
        ),
    )
    @field_validator('prompt')
    @classmethod
    def sanitize_prompt(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El prompt no puede estar vacío")
        # Remove null bytes and control chars (except newlines and tabs)
        v = ''.join(c for c in v if c >= ' ' or c in '\n\t')
        return v

    # ── Multimodalidad ──────────────────────────────────────────────────────
    images: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de imágenes en base64 (con o sin data URI prefix). "
            "Solo para modelos multimodales como llava, bakllava, moondream. "
            "Ejemplo: ['data:image/png;base64,iVBOR...'] o ['iVBOR...']"
        ),
    )
    image_detail: str = Field(
        default="auto",
        description="Nivel de detalle para análisis de imágenes: auto | low | high",
    )
    # ── Contexto de conversación ─────────────────────────────────────────────
    conversation_history: list[dict] = Field(
        default_factory=list,
        description=(
            "Historial de mensajes previos para contexto multi-turn. "
            "Formato: [{'role': 'user'|'assistant', 'content': '...'}]"
        ),
    )
    context_window: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Número máximo de mensajes anteriores a incluir como contexto",
    )
    # ── Memoria semántica ───────────────────────────────────────────────────
    use_memory: bool = Field(
        default=False,
        description="Si True, busca en la memoria semántica antes de responder",
    )
    memory_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Número de memorias relevantes a recuperar",
    )


class ChatChunk(BaseModel):
    """
    Un fragmento de respuesta en modo streaming SSE.
    El cliente recibe estos chunks mientras el modelo genera.
    El último chunk tiene is_final=True y lleva los metadatos completos.
    """

    chunk_id: str = Field(description="UUID único de este chunk")
    request_id: str = Field(description="UUID del request al que pertenece")
    content: str = Field(description="Tokens de texto de este chunk")
    specialist_id: str | None = Field(
        default=None,
        description="ID del especialista que generó este chunk (útil en staircase streaming)",
    )
    is_final: bool = Field(
        default=False,
        description="True en el último chunk. Cuando es True, 'metadata' contiene el resumen.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Solo presente en el chunk final: latencia, estrategia, trace_id, etc.",
    )


class ChatResponse(BaseModel):
    """
    Respuesta completa del chat (modo no-streaming).
    Contiene el texto final y todos los metadatos de la ejecución.
    """

    request_id: str = Field(description="UUID único de esta petición")
    response: str = Field(description="Texto de la respuesta final")
    specialists_used: list[str] = Field(description="IDs de los especialistas que respondieron")
    strategy_used: str = Field(description="Estrategia de fusión que se aplicó")
    latency_ms: float = Field(description="Tiempo total de la petición en milisegundos")
    ttft_ms: float = Field(
        default=0.0,
        description="Time To First Token — milisegundos hasta el primer token generado",
    )
    hardware_tier: int = Field(description="Tier de hardware activo (1–4)")
    policy_applied: str = Field(description="Nombre de la política de hardware aplicada")
    degraded: bool = Field(
        default=False,
        description="True si el sistema tuvo que reducir calidad por falta de VRAM",
    )
    degradation_reason: str | None = Field(
        default=None,
        description="Explicación de por qué se degradó (si degraded=True)",
    )
    trace_id: str = Field(description="Referencia al TraceRecord en la base de datos")
    power_tier: int | None = Field(
        default=None, description="Nivel de potencia aplicado por el orquestador lineal (1-4)")
    power_reason: str | None = Field(
        default=None, description="Explicación de la decisión de potencia")
    models_used: dict[str, str] | None = Field(
        default=None, description="Mapa especialista→modelo realmente usado")
    error_kind: str | None = Field(
        default=None,
        description="Tipo de error para que la UI lo muestre bien: 'ollama_offline', 'model_missing' o None",
    )


# ══════════════════════════════════════════════════════════════════════════════
# ESPECIALISTAS
# ══════════════════════════════════════════════════════════════════════════════

class SpecialistProfile(BaseModel):
    """
    Perfil de un especialista en el catálogo de Andromeda.
    Cada especialista es un modelo Ollama + system prompt especializado.
    """

    id: str = Field(description="Identificador único (ej: 'software-engineering')")
    name: str = Field(description="Nombre legible (ej: 'Software Engineering AI')")
    model_name: str = Field(
        default="PENDIENTE_CONFIGURAR",
        description=(
            "Nombre exacto del modelo en Ollama. "
            "Cambiar en config/specialists.yaml. "
            "El sistema no activará este especialista mientras sea 'PENDIENTE_CONFIGURAR'."
        ),
    )
    domain: str = Field(description="Dominio principal (ej: 'Software development')")
    description: str = Field(description="Descripción de una línea del especialista")
    active: bool = Field(
        default=False,
        description="Si False, el especialista no se usará aunque esté configurado",
    )
    system_prompt: str = Field(
        default="",
        description="Instrucciones de comportamiento para el modelo. Definidas en profiles.py.",
    )
    vram_required_gb: float = Field(
        default=4.0,
        description="VRAM estimada en GB que consume este modelo cuando está cargado",
    )
    min_tier: int = Field(
        default=1,
        description="Tier mínimo de hardware necesario para activar este especialista (1–4)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE
# ══════════════════════════════════════════════════════════════════════════════

class HardwareInfo(BaseModel):
    """
    Información del hardware detectado al arranque del sistema.
    La detecta HardwareDetector y se guarda en app.state.hardware.
    """

    os: str = Field(description="Sistema operativo: 'Windows', 'Darwin' (macOS), 'Linux'")
    cpu_model: str = Field(description="Nombre del procesador")
    cpu_cores: int = Field(description="Número de núcleos físicos")
    ram_total_gb: float = Field(description="RAM total en GB")
    ram_available_gb: float = Field(description="RAM disponible ahora mismo en GB")
    gpus: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de GPUs detectadas. Cada una: {name, vram_total_gb, vram_free_gb}",
    )
    total_vram_gb: float = Field(
        default=0.0,
        description="Suma de VRAM de todas las GPUs en GB. 0 si no hay GPU.",
    )
    acceleration: str = Field(
        default="cpu",
        description="Tipo de aceleración: 'cuda' | 'rocm' | 'metal' | 'cpu'",
    )
    max_tier: int = Field(
        default=1,
        description="Tier máximo que puede alcanzar este hardware (1–4)",
    )


class HardwarePolicy(BaseModel):
    """
    Política derivada del hardware detectado.
    Define cómo debe comportarse el sistema en este hardware.
    Cargada desde hardware_policies.yaml por el PolicyEngine.
    """

    tier: int = Field(description="Tier de esta política (1–4)")
    max_parallel: int = Field(description="Máximo de especialistas en paralelo")
    recommended_quant: str = Field(
        description="Cuantización óptima: 'Q4_K_M' | 'Q5_K_M' | 'Q8_0' | 'fp16'"
    )
    max_context_tokens: int = Field(description="Longitud máxima de contexto segura en tokens")
    strategy_budget: str = Field(
        description="Presupuesto de estrategia: 'conservative' | 'balanced' | 'aggressive'"
    )
    can_run_verifier: bool = Field(
        description="Si hay VRAM suficiente para añadir el especialista verifier"
    )
    safe_vram_threshold_gb: float = Field(
        description="Umbral de VRAM libre bajo el cual se activa la degradación de seguridad"
    )
    eligible_strategies: list[str] = Field(
        description="Lista de estrategias disponibles en este tier"
    )


@dataclass
class RuntimePolicy:
    """
    Política derivada para UN request concreto.
    El PolicyEngine combina la política base del tier con el estado
    actual de la VRAM para producir esta política dinámica.

    Nota: usamos dataclass (no Pydantic) porque es interna al sistema
    y no necesita serialización JSON.
    """

    # Lo que realmente se va a hacer en este request
    effective_parallel: int = 1
    effective_strategy: str = "single"
    effective_specialists: list[str] = field(default_factory=list)

    # Si el sistema tuvo que bajar de lo que pedía el usuario
    degraded: bool = False
    degradation_reason: str | None = None

    # Info del hardware en el momento del request
    vram_free_gb: float = 0.0
    hardware_tier: int = 1
    policy_name: str = "T1_conservative"


# ══════════════════════════════════════════════════════════════════════════════
# OBSERVABILIDAD
# ══════════════════════════════════════════════════════════════════════════════

class TraceRecord(BaseModel):
    """
    Registro completo de una petición.
    Se guarda en SQLite y es consultable vía GET /api/traces/{id}.
    Contiene toda la información necesaria para auditar qué pasó.
    """

    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID único de este trace",
    )
    request_id: str = Field(description="UUID del request al que corresponde")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Fecha y hora UTC en formato ISO 8601",
    )

    # Resumen de la petición (sin guardar el prompt completo por privacidad)
    prompt_preview: str = Field(
        default="",
        description="Primeros 100 caracteres del prompt. No se guarda el texto completo.",
    )

    # Ejecución
    strategy: str = Field(default="", description="Estrategia solicitada por el usuario")
    strategy_effective: str = Field(default="", description="Estrategia que realmente se aplicó")
    specialists_used: list[str] = Field(
        default_factory=list,
        description="IDs de los especialistas que respondieron",
    )
    degraded: bool = Field(default=False, description="Si el sistema tuvo que degradar")
    degradation_reason: str | None = Field(default=None)

    # Métricas de rendimiento
    latency_ms: float = Field(default=0.0, description="Latencia total en ms")
    ttft_ms: float = Field(default=0.0, description="Time To First Token en ms")

    # Hardware en el momento de la petición
    hardware_tier: int = Field(default=1)
    vram_free_gb: float = Field(default=0.0)
    policy_applied: str = Field(default="")

    # Clasificación
    classifier_source: str = Field(
        default="keywords",
        description="Fuente del clasificador: 'llm' | 'keywords' | 'forced'",
    )
    classifier_confidence: float = Field(default=0.0)
    routing_reasoning: str = Field(
        default="",
        description="Explicación en lenguaje natural de las decisiones del orquestador",
    )

    # Resultado
    success: bool = Field(default=True)
    error: str | None = Field(default=None, description="Mensaje de error si success=False")

    # Árbol completo de spans OpenTelemetry (serializado como JSON)
    spans: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Árbol de spans con tiempos de cada componente",
    )


@dataclass
class OrchestratorDecision:
    """
    Registro de todas las decisiones que tomó el orquestador para un request.
    Se incluye en el TraceRecord como parte del routing_reasoning.
    """

    request_id: str

    # Clasificación
    classifier_source: str = "keywords"       # "llm" | "keywords" | "forced"
    classifier_confidence: float = 0.0
    classifier_raw_output: dict = field(default_factory=dict)

    # Selección de especialistas
    specialists_considered: list[str] = field(default_factory=list)
    specialists_selected: list[str] = field(default_factory=list)
    selection_reason: str = ""

    # Estrategia
    strategy_requested: str = "auto"
    strategy_effective: str = "single"
    strategy_downgraded: bool = False
    strategy_downgrade_reason: str | None = None

    # Hardware en el momento
    hardware_tier: int = 1
    vram_free_gb: float = 0.0
    policy_name: str = "T1_conservative"

    # Texto legible del razonamiento completo
    routing_reasoning: str = ""
