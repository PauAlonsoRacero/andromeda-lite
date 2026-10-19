"""
vision.py — Imágenes adjuntas al chat.

Antes: siempre `llava:7b` (instalado o no), y se le pasaba la pregunta del
usuario tal cual como instrucción. llava es pequeño y en un caso real describió
una captura en portugués. Además se ignoraba que muchos modelos de chat actuales
ven imágenes por sí mismos.

Ahora:
  1. Si el modelo de chat de la respuesta ve imágenes, las recibe directamente
     (como hace Claude): mejor calidad, sin un paso intermedio.
  2. Si no, se elige el mejor modelo de visión instalado y se le pide una
     descripción exhaustiva —incluido el texto visible— en el idioma de la
     interfaz. El modelo de chat responde a partir de esa descripción.
  3. Si no hay ninguno, se avisa al usuario de qué instalar, en vez de fingir
     que ha visto la imagen.
"""
from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger("andromeda.vision")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:
        @staticmethod
        def log(*a, **k): pass
    diag = _Nulo()

# De mejor a peor para describir capturas y documentos.
_PREFERENCIA = ("qwen3.8", "gemma4", "qwen2.5vl", "qwen2.5-vl", "qwen2-vl", "gemma3", "llama3.2-vision",
                "minicpm-v", "granite3.2-vision", "mistral-small3", "llava-llama3",
                "llava-phi3", "llava", "bakllava", "moondream")


def is_vision_model(nombre: str) -> bool:
    """¿El modelo acepta imágenes? gemma3:1b es la excepción conocida."""
    n = (nombre or "").lower()
    if n.startswith("gemma3:1b") or n.startswith("gemma3:270m"):
        return False
    return any(n.startswith(f) or f"/{f}" in n for f in _PREFERENCIA)


def pick_vision_model(disponibles: list[str]) -> str | None:
    for familia in _PREFERENCIA:
        for m in disponibles or []:
            if m.lower().startswith(familia) and is_vision_model(m):
                return m
    return None


_INSTRUCCION = {
    "es": "Describe esta imagen con todo detalle para alguien que no puede verla. "
          "Transcribe literalmente todo el texto visible. Indica qué tipo de imagen es "
          "(captura de pantalla, foto, diagrama, documento…). Responde en español.",
    "en": "Describe this image in full detail for someone who cannot see it. Transcribe "
          "all visible text verbatim. Say what kind of image it is (screenshot, photo, "
          "diagram, document…). Answer in English.",
    "de": "Beschreibe dieses Bild ausführlich für jemanden, der es nicht sehen kann. "
          "Gib allen sichtbaren Text wörtlich wieder. Antworte auf Deutsch.",
    "fr": "Décris cette image en détail pour quelqu'un qui ne peut pas la voir. "
          "Retranscris tout le texte visible. Réponds en français.",
    "zh": "请为看不到这张图片的人详细描述它，并逐字转录所有可见文字。用中文回答。",
}


def _idioma() -> str:
    lang = (os.environ.get("ANDROMEDA_LANGUAGE") or "en").lower()[:2]
    return lang if lang in _INSTRUCCION else "en"


def strip_data_url(imagen: str) -> str:
    """Ollama espera base64 puro, sin el prefijo data:image/…;base64,"""
    return imagen.split(",", 1)[1] if imagen.startswith("data:") and "," in imagen else imagen


async def describe(imagenes: list[str], ollama_url: str, modelo: str,
                   timeout: float = 120.0) -> str:
    """Descripción detallada, en el idioma de la interfaz."""
    lang = _idioma()
    async with httpx.AsyncClient(trust_env=False) as c:
        r = await c.post(f"{ollama_url}/api/chat", json={
            "model": modelo,
            "messages": [{"role": "user", "content": _INSTRUCCION[lang],
                          "images": [strip_data_url(i) for i in imagenes[:3]]}],
            "options": {"temperature": 0.2, "num_predict": 1200},
            "keep_alive": os.environ.get("ANDROMEDA_KEEP_ALIVE") or "30m",
            "stream": False,
        }, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    texto = (r.json().get("message") or {}).get("content", "")
    # Quitar razonamiento interno si el modelo lo emite.
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()


_SIN_MODELO = {
    "es": "El usuario ha adjuntado una imagen, pero no hay ningún modelo de visión instalado, "
          "así que NO puedes verla. Díselo con claridad y sugiérele instalar uno, por ejemplo: "
          "`ollama pull qwen2.5vl:7b`. No inventes lo que contiene la imagen.",
    "en": "The user attached an image, but no vision model is installed, so you CANNOT see it. "
          "Say so clearly and suggest installing one, e.g. `ollama pull qwen2.5vl:7b`. "
          "Do not invent what the image contains.",
}


def no_model_notice() -> str:
    return _SIN_MODELO.get(_idioma(), _SIN_MODELO["en"])
