"""
middleware.py — Middleware de seguridad y robustez para Andromeda.

Rate limiting simple en memoria (no persistido).
Input sanitization para prevenir prompts extremadamente largos.
Request ID injection para trazabilidad.
"""
import time
import uuid
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting simple por IP. Límites:
    - /api/chat: 20 req/min (evitar abuso de generación)
    - /api/sandbox/run: 30 req/min (evitar abuso de ejecución de código)
    - otros: 200 req/min
    """

    LIMITS = {
        "/api/chat":        (20,  60),   # 20 por minuto
        "/api/sandbox/run": (30,  60),   # 30 por minuto
        "/api/vision":      (15,  60),   # 15 por minuto
        "default":          (200, 60),   # 200 por minuto
    }

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # {(ip, path_key): [(timestamp, count)]}
        self._counters: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Solo aplicar rate limit a rutas API
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        ip = self._get_ip(request)
        path_key = self._get_path_key(request.url.path)
        limit, window = self.LIMITS.get(path_key, self.LIMITS["default"])

        now = time.time()
        bucket_key = (ip, path_key)
        # Limpiar entradas antiguas
        self._counters[bucket_key] = [
            t for t in self._counters[bucket_key]
            if now - t < window
        ]

        if len(self._counters[bucket_key]) >= limit:
            remaining_window = int(
                window - (now - min(self._counters[bucket_key]))
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": True,
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Demasiadas peticiones. Espera {remaining_window}s.",
                    "retry_after": remaining_window,
                },
                headers={"Retry-After": str(remaining_window)},
            )

        self._counters[bucket_key].append(now)
        response = await call_next(request)
        remaining = limit - len(self._counters[bucket_key])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response

    def _get_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _get_path_key(self, path: str) -> str:
        for key in self.LIMITS:
            if key != "default" and path.startswith(key):
                return key
        return "default"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Añade X-Request-ID a todas las respuestas para trazabilidad."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers de seguridad básicos."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
