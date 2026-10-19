"""
model_health.py — Circuit breaker de modelos (Andromeda Pro).

Si un modelo falla repetidamente (Ollama caído para ese modelo, OOM, timeouts),
se "abre el circuito": el modelo queda en cuarentena un cooldown y el routing
lo evita, degradando a otro modelo instalado en vez de fallar en cadena.
Patrón clásico de resiliencia (Nygard, "Release It!") aplicado a serving local.

Estados: closed (sano) → open (en cuarentena tras N fallos en ventana) →
half-open (probar de nuevo tras cooldown; un éxito lo cierra).
"""
from __future__ import annotations

import threading
import time

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


_FAILS_TO_OPEN = 3        # fallos consecutivos para abrir
_WINDOW_S = 120.0         # ventana en la que cuentan los fallos
_COOLDOWN_S = 60.0        # cuarentena antes de half-open

_lock = threading.Lock()
_state: dict[str, dict] = {}   # model -> {fails, first_fail_ts, opened_ts}


def record_failure(model: str) -> None:
    if not model:
        return
    now = time.monotonic()
    with _lock:
        st = _state.setdefault(model, {"fails": 0, "first_fail_ts": now, "opened_ts": 0.0})
        if now - st["first_fail_ts"] > _WINDOW_S:      # ventana caducada → reset
            st["fails"], st["first_fail_ts"] = 0, now
        st["fails"] += 1
        if st["fails"] >= _FAILS_TO_OPEN and not st["opened_ts"]:
            st["opened_ts"] = now


def record_success(model: str) -> None:
    if not model:
        return
    with _lock:
        _state.pop(model, None)                        # éxito → circuito cerrado


def is_available(model: str) -> bool:
    """False solo mientras el modelo está en cuarentena (circuito abierto)."""
    if not model:
        return True
    now = time.monotonic()
    with _lock:
        st = _state.get(model)
        if not st or not st["opened_ts"]:
            return True
        if now - st["opened_ts"] >= _COOLDOWN_S:       # half-open: dejar probar
            st["opened_ts"] = 0.0
            st["fails"] = _FAILS_TO_OPEN - 1           # un fallo más lo reabre
            return True
        return False


def snapshot() -> dict:
    """Estado para observabilidad (/api/health/models)."""
    now = time.monotonic()
    with _lock:
        return {m: {"fails": st["fails"],
                    "open": bool(st["opened_ts"] and now - st["opened_ts"] < _COOLDOWN_S),
                    "cooldown_left_s": max(0, round(_COOLDOWN_S - (now - st["opened_ts"]))) if st["opened_ts"] else 0}
                for m, st in _state.items()}


def pick_healthy(preferred: str, alternatives: list[str]) -> str:
    """El preferido si está sano; si no, la primera alternativa sana; si no, el preferido."""
    if is_available(preferred):
        return preferred
    for alt in alternatives or []:
        if alt != preferred and is_available(alt):
            return alt
    return preferred
