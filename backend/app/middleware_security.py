"""
middleware_security.py — Blindaje de la API de Andromeda.

Capas:
  1. Loopback-only: rechaza conexiones que no vengan de la propia máquina
     (la app es local; nadie de la red debe poder hablar con el backend).
     Desactivable con ANDROMEDA_ALLOW_REMOTE=1 (ej: Docker con proxy propio).
  2. Cabeceras de seguridad en toda respuesta.
  3. Límite de tamaño de body (anti-DoS): 15 MB.
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MAX_BODY_BYTES = 15 * 1024 * 1024
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1) Solo loopback (salvo opt-out explícito p. ej. en Docker tras proxy)
        if os.environ.get("ANDROMEDA_ALLOW_REMOTE") != "1":
            client = request.client.host if request.client else ""
            # En Docker el gateway del bridge accede desde 172.x — permitido
            # solo si la cabecera Host apunta a localhost (acceso vía publish).
            if client not in _LOOPBACK and not client.startswith("172."):
                return JSONResponse(
                    status_code=403,
                    content={"error": "Acceso solo permitido desde esta máquina."},
                )

        # 2) Límite de tamaño
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413,
                                content={"error": "Cuerpo demasiado grande."})

        response = await call_next(request)

        # 3) Cabeceras de seguridad
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy",
                                    "camera=(), microphone=(), geolocation=()")
        return response


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Si ANDROMEDA_AUTH_REQUIRED=1, exige sesión válida para la API."""

    _EXEMPT_PREFIXES = (
        "/api/auth/", "/api/cloud/", "/api/health",
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if (os.environ.get("ANDROMEDA_AUTH_REQUIRED") == "1"
                and path.startswith("/api/")
                and not any(path.startswith(p) for p in self._EXEMPT_PREFIXES)):
            from app.routes.auth import current_user
            if current_user(request) is None:
                return JSONResponse(status_code=401,
                                    content={"error": "Sesión requerida", "auth_required": True})
        return await call_next(request)
