"""
multimodal.py — Análisis de imágenes con modelos vision de Andromeda.

POST /api/vision/analyze   → analizar una imagen con una pregunta
POST /api/vision/describe  → describir una imagen automáticamente
GET  /api/vision/models    → modelos vision disponibles en Ollama

Modelos soportados:
  llava:7b       — LLaVA 7B, el más ligero (~4.5GB VRAM)
  llava:13b      — LLaVA 13B, mayor calidad (~8GB VRAM)
  llava:34b      — LLaVA 34B, máxima calidad (~20GB VRAM)
  moondream:1.8b — Moondream ultra-ligero (~1.5GB VRAM)
  bakllava:7b    — BakLLaVA, bueno en razonamiento visual

Uso desde la UI:
  El usuario arrastra/pega una imagen en el chat
  El frontend la convierte a base64
  Se envía como parte del ChatRequest (campo images=[])
  El backend detecta que hay imágenes y usa un modelo vision
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx

logger = logging.getLogger("andromeda.multimodal")
router = APIRouter()

VISION_MODELS = ["llava:7b", "llava:13b", "moondream:1.8b", "bakllava:7b", "llava:34b"]


@router.get("/models")
async def get_vision_models(request: Request) -> JSONResponse:
    """Retorna los modelos vision disponibles en Ollama."""
    settings = request.app.state.settings
    available = []
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
            if r.status_code == 200:
                installed = {m["name"] for m in r.json().get("models", [])}
                for model in VISION_MODELS:
                    available.append({
                        "name":      model,
                        "installed": model in installed,
                        "pull_cmd":  f"ollama pull {model}",
                    })
    except Exception:
        pass
    return JSONResponse(content={"models": available, "vision_models": VISION_MODELS})


@router.post("/analyze")
async def analyze_image(request: Request) -> JSONResponse:
    """
    Analiza una imagen con una pregunta del usuario.

    Body: {
        "image": "base64_string_or_data_uri",
        "question": "¿Qué muestra esta imagen?",
        "model": "llava:7b"  (opcional)
    }
    """
    settings = request.app.state.settings
    body     = await request.json()
    image_b64 = body.get("image", "")
    question  = body.get("question", "Describe esta imagen en detalle")
    model     = body.get("model", "llava:7b")

    if not image_b64:
        return JSONResponse(status_code=400, content={"error": "image requerida (base64)"})

    # Limpiar data URI si la tiene
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model":   model,
                    "messages": [{
                        "role":    "user",
                        "content": question,
                        "images":  [image_b64],
                    }],
                    "options": {"temperature": 0.3, "num_predict": 1024},
                    "stream":  False,
                },
                timeout=60.0,
            )
            r.raise_for_status()
            response = r.json().get("message", {}).get("content", "")

        return JSONResponse(content={
            "response": response,
            "model":    model,
            "question": question,
        })
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return JSONResponse(status_code=404, content={
                "error": f"Modelo '{model}' no instalado. Descárgalo con: ollama pull {model}"
            })
        return JSONResponse(status_code=500, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/describe")
async def describe_image(request: Request) -> JSONResponse:
    """Describe automáticamente una imagen sin pregunta específica."""
    body = await request.json()
    body["question"] = (
        "Describe esta imagen en detalle. Incluye: qué se ve, colores principales, "
        "texto visible si lo hay, y cualquier información relevante sobre el contexto."
    )
    return await analyze_image(request)
