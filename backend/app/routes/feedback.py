"""
feedback.py (rutas) — API de feedback de usuario sobre las respuestas.

POST /api/feedback   → registra 👍/👎 (y lo enlaza al experimento A/B si aplica)
GET  /api/feedback   → estadísticas de satisfacción
"""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.routes.feedback")
router = APIRouter()


@router.post("")
async def submit_feedback(request: Request) -> JSONResponse:
    body = await request.json()
    positive = bool(body.get("positive", True))
    request_id = (body.get("request_id") or "").strip()
    model = body.get("model")
    comment = body.get("comment")

    store = getattr(request.app.state, "feedback_store", None)
    if store is not None:
        try:
            store.record(request_id, positive, model=model, comment=comment)
        except Exception as e:
            logger.warning(f"feedback.record falló: {e}")

    # Si la respuesta formó parte de un experimento A/B, este voto es señal de
    # CALIDAD para la variante que la sirvió.
    exp = body.get("ab_experiment")
    variant = body.get("ab_variant")
    if exp and variant:
        ab = getattr(request.app.state, "ab_testing", None)
        if ab is not None:
            try:
                ab.record_quality(exp, variant, positive)
            except Exception as e:
                logger.warning(f"ab.record_quality falló: {e}")

    return JSONResponse(content={"success": True})


@router.get("")
async def feedback_stats(request: Request) -> JSONResponse:
    store = getattr(request.app.state, "feedback_store", None)
    if store is None:
        return JSONResponse(content={"total": 0, "satisfaction": None})
    return JSONResponse(content=store.stats())
