"""
tracer.py — Sistema de trazabilidad de Andromeda.

Wrapping ligero de OpenTelemetry que genera spans por petición
y los persiste en SQLite via TraceStore.

Cada request genera un árbol de spans:
  span: process_request
    event: hardware_state
    event: classifier_result
    event: policy_applied
    span: executor
      span: specialist:sw-engineering
      span: specialist:verifier
    span: merger:iterative_refine
    event: request_complete

Uso:
    tracer = AndromedalTracer(store)
    tracer.start_span(request_id, "process_request")
    tracer.add_event(request_id, "classifier_result", {"source": "keywords"})
    tracer.end_span(request_id, trace_record)
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.observability.store import TraceStore

logger = logging.getLogger("andromeda.tracer")


class AndromedalTracer:
    """
    Tracer de Andromeda con spans OpenTelemetry y persistencia SQLite.

    Guarda en memoria los spans activos y los persiste al finalizar.
    Los spans son ligeros: solo nombre, tiempo de inicio y eventos.
    """

    def __init__(self, store: TraceStore) -> None:
        """
        Args:
            store: TraceStore donde se persistirán los traces completados
        """
        self._store = store
        # Diccionario de spans activos: {request_id: SpanContext}
        self._active_spans: dict[str, dict] = defaultdict(lambda: {
            "name": "",
            "start_time": 0.0,
            "events": [],
            "children": [],
        })

    def start_span(self, request_id: str, operation: str) -> None:
        """
        Inicia un span para el request_id dado.

        Args:
            request_id: UUID del request
            operation: Nombre de la operación (ej: "process_request")
        """
        self._active_spans[request_id] = {
            "name": operation,
            "start_time": time.perf_counter(),
            "start_timestamp": datetime.now(timezone.utc).isoformat(),
            "events": [],
            "children": [],
        }
        logger.debug(f"[{request_id[:8]}] Span iniciado: {operation}")

    def add_event(self, request_id: str, event_name: str, attributes: dict | None = None) -> None:
        """
        Añade un evento al span activo del request_id.

        Los eventos son hitos dentro de un span (no tienen duración propia).
        Ejemplos: "hardware_detected", "classifier_result", "policy_applied"

        Args:
            request_id: UUID del request
            event_name: Nombre del evento
            attributes: Datos adicionales del evento (opcionales)
        """
        if request_id not in self._active_spans:
            return

        event = {
            "name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round(
                (time.perf_counter() - self._active_spans[request_id]["start_time"]) * 1000, 1
            ),
            "attributes": attributes or {},
        }
        self._active_spans[request_id]["events"].append(event)
        logger.debug(f"[{request_id[:8]}] Evento: {event_name} {attributes or ''}")

    def add_child_span(
        self,
        request_id: str,
        span_name: str,
        duration_ms: float,
        attributes: dict | None = None,
    ) -> None:
        """
        Añade un span hijo al span activo del request.

        Útil para registrar la duración de cada especialista y el merger.

        Args:
            request_id: UUID del request
            span_name: Nombre del span hijo (ej: "specialist:sw-engineering")
            duration_ms: Duración del span hijo en milisegundos
            attributes: Datos adicionales (ej: {model, success, latency_ms})
        """
        if request_id not in self._active_spans:
            return

        child = {
            "name": span_name,
            "duration_ms": round(duration_ms, 1),
            "attributes": attributes or {},
        }
        self._active_spans[request_id]["children"].append(child)
        logger.debug(f"[{request_id[:8]}] Child span: {span_name} ({duration_ms:.0f}ms)")

    async def end_span(self, request_id: str, trace: object) -> None:
        """
        Finaliza el span activo, calcula la duración y persiste el TraceRecord.

        Llama a TraceStore.save() de forma async (no bloquea).
        Si hay un error al persistir, solo se logea — no lanza excepción.

        Args:
            request_id: UUID del request
            trace: TraceRecord a persistir
        """
        if request_id not in self._active_spans:
            logger.warning(f"end_span para request_id desconocido: {request_id[:8]}")
            return

        span_data = self._active_spans.pop(request_id)
        total_duration = (time.perf_counter() - span_data["start_time"]) * 1000

        # Construir el árbol de spans completo para el TraceRecord
        span_tree = {
            "name": span_data["name"],
            "duration_ms": round(total_duration, 1),
            "events": span_data["events"],
            "children": span_data["children"],
        }

        # Añadir el árbol de spans al trace
        if hasattr(trace, "spans"):
            trace.spans = [span_tree]

        # Persistir el trace en SQLite
        await self._store.save(trace)
        logger.debug(f"[{request_id[:8]}] Trace completado: {total_duration:.0f}ms")

    def build_routing_reasoning(
        self,
        classifier_result: dict,
        runtime_policy: object,
        hardware_info: object,
    ) -> str:
        """
        Construye una explicación en lenguaje natural de las decisiones del orquestador.

        Esta explicación es lo que hace a Andromeda auditable:
        cualquiera puede entender por qué el sistema tomó las decisiones que tomó.

        Returns:
            String con la explicación completa
        """
        specialists = classifier_result.get("specialists", [])
        strategy = classifier_result.get("strategy", "unknown")
        confidence = classifier_result.get("confidence", 0.0)
        source = classifier_result.get("source", "keywords")
        tier = getattr(hardware_info, "max_tier", 1)
        vram_free = getattr(runtime_policy, "vram_free_gb", 0.0)
        degraded = getattr(runtime_policy, "degraded", False)
        policy_name = getattr(runtime_policy, "policy_name", "unknown")

        lines = []

        # Clasificación
        if source == "llm":
            lines.append(
                f"Clasificador LLM seleccionó {specialists} "
                f"(confianza: {confidence:.0%})."
            )
        elif source == "keywords":
            reasoning = classifier_result.get("reasoning", "")
            lines.append(f"Clasificador keywords: {reasoning}")
        else:
            lines.append(f"Selección forzada por el usuario: {specialists}.")

        # Hardware y política
        lines.append(
            f"Hardware T{tier}, política '{policy_name}'. "
            f"VRAM libre: {vram_free:.1f}GB."
        )

        # Degradación
        if degraded:
            reason = getattr(runtime_policy, "degradation_reason", "")
            lines.append(f"⚠️ Degradación activa: {reason}")
        else:
            lines.append("Sin degradación — recursos suficientes.")

        # Estrategia
        lines.append(f"Estrategia aplicada: {strategy}.")

        return " ".join(lines)
