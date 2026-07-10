"""
routes/cloud_routes.py — Puente entre el frontend de Andromeda y Andromeda Cloud.

El frontend habla con estos endpoints locales; el backend reenvía al servicio
cloud y gestiona la sesión/licencia en local. Así el frontend no necesita saber
la URL del cloud ni manejar la clave pública.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..cloud import client as cloud

router = APIRouter(prefix="/api/cloud", tags=["cloud"])


@router.get("/status")
async def status() -> JSONResponse:
    """Estado de la cuenta cloud y plan efectivo (validado offline)."""
    sess = cloud.load_session()
    plan = cloud.current_plan()
    return JSONResponse(content={
        "logged_in": bool(sess),
        "user": sess.get("user") if sess else None,
        "plan": plan,
    })


@router.post("/register")
async def register(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        user = cloud.register(
            email=body.get("email", ""),
            password=body.get("password", ""),
            display_name=body.get("display_name", ""),
            country=body.get("country", ""),
        )
        return JSONResponse(content={"success": True, "user": user, "plan": cloud.current_plan()})
    except cloud.CloudError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con el servicio. ¿Tienes conexión?"})


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        user = cloud.login(email=body.get("email", ""), password=body.get("password", ""))
        return JSONResponse(content={"success": True, "user": user, "plan": cloud.current_plan()})
    except cloud.CloudError as e:
        return JSONResponse(status_code=401, content={"error": str(e)})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con el servicio. ¿Tienes conexión?"})


@router.post("/logout")
async def logout() -> JSONResponse:
    cloud.logout()
    return JSONResponse(content={"success": True})


@router.post("/refresh")
async def refresh() -> JSONResponse:
    """Revalida sesión + licencia (al abrir la app o tras un pago)."""
    user = cloud.refresh_profile()
    return JSONResponse(content={"user": user, "plan": cloud.current_plan()})


@router.post("/upgrade")
async def upgrade() -> JSONResponse:
    """Devuelve la URL de pago de Stripe para suscribirse a Pro."""
    url = cloud.start_checkout()
    if not url:
        return JSONResponse(status_code=400, content={"error": "Inicia sesión primero"})
    return JSONResponse(content={"checkout_url": url})


@router.get("/export")
async def export_data() -> JSONResponse:
    """Exporta todos los datos del usuario (RGPD)."""
    data = cloud.export_data()
    if data is None:
        return JSONResponse(status_code=401, content={"error": "Inicia sesión primero"})
    return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=andromeda-mis-datos.json"})


@router.delete("/account")
async def delete_account() -> JSONResponse:
    """Borra la cuenta y todos los datos del usuario (RGPD)."""
    ok = cloud.delete_account()
    return JSONResponse(content={"deleted": ok})
