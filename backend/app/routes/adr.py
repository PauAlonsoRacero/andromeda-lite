"""
adr.py — Generador de ADRs con IA.

Los ADRs (Architecture Decision Records) son documentos que registran
decisiones técnicas importantes. Este endpoint genera ADRs completos
usando las IAs de Andromeda.

Formato: MADR (Markdown Architecture Decision Records)
"""

import logging
import datetime
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.adr")
router = APIRouter()

ADR_SYSTEM_PROMPT = """Eres un arquitecto de software senior experto en documentar decisiones técnicas.
Tu tarea es generar Architecture Decision Records (ADRs) completos y profesionales en formato MADR.

Un ADR debe incluir:
1. Título descriptivo
2. Estado (Proposed/Accepted/Deprecated/Superseded)
3. Contexto y problema
4. Opciones consideradas (con pros y contras de cada una)
5. Decisión tomada y justificación
6. Consecuencias positivas y negativas
7. Pros y contras de las opciones no elegidas

Formato MADR estricto con secciones en Markdown.
Sé específico, técnico y directo. No uses lenguaje vago."""


@router.post("/generate")
async def generate_adr(request: Request) -> JSONResponse:
    """
    Genera un ADR completo a partir de una descripción de la decisión.

    Body: {
        "decision": "Usar FastAPI en lugar de Flask",
        "context": "Necesitamos un framework async para SSE",
        "options": ["FastAPI", "Flask", "Django"],
        "chosen": "FastAPI",
        "project": "Andromeda"
    }
    """
    import httpx
    body     = await request.json()
    decision = body.get("decision", "")
    context  = body.get("context", "")
    options  = body.get("options", [])
    chosen   = body.get("chosen", "")
    project  = body.get("project", "Sistema")
    adr_num  = body.get("number", 1)

    if not decision:
        return JSONResponse(status_code=400, content={"error": "decision requerida"})

    settings = request.app.state.settings
    registry = request.app.state.registry

    # Usar technical-writer o generalist
    active  = registry.get_active()
    writer  = next((s for s in active if s.id in ('technical-writer','generalist')), None)
    model   = writer.model_name if writer else "mistral:7b"

    options_text = "\n".join(f"- {o}" for o in options) if options else "No especificadas"
    prompt = f"""Genera un ADR completo para el proyecto {project}.

DECISIÓN: {decision}
CONTEXTO ADICIONAL: {context or 'No especificado'}
OPCIONES CONSIDERADAS: {options_text}
OPCIÓN ELEGIDA: {chosen or 'No especificada'}
NÚMERO DE ADR: {adr_num}
FECHA: {datetime.date.today().isoformat()}

Genera el ADR completo en formato MADR con todas las secciones.
Incluye pros y contras de cada opción, consecuencias de la decisión, y referencias si aplica."""

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model":    model,
                    "messages": [
                        {"role": "system", "content": ADR_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    "options": {"temperature": 0.2, "num_predict": 2000},
                    "stream":  False,
                },
                timeout=60.0,
            )
            r.raise_for_status()
            adr_content = r.json().get("message", {}).get("content", "")

        # Generar nombre de archivo
        slug = decision.lower().replace(" ", "-")[:50]
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        filename = f"ADR-{adr_num:03d}-{slug}.md"

        return JSONResponse(content={
            "success":  True,
            "filename": filename,
            "content":  adr_content,
            "model":    model,
            "number":   adr_num,
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/list-templates")
async def list_templates(request: Request) -> JSONResponse:
    """Retorna templates de decisiones técnicas comunes."""
    templates = [
        {"id":"framework",   "title":"Elección de framework",      "description":"Comparar frameworks web, ML, etc."},
        {"id":"database",    "title":"Elección de base de datos",   "description":"SQL vs NoSQL, RDBMS específico"},
        {"id":"architecture","title":"Decisión arquitectónica",      "description":"Monolito vs microservicios, etc."},
        {"id":"library",     "title":"Elección de librería",        "description":"Comparar librerías para una función"},
        {"id":"pattern",     "title":"Patrón de diseño",            "description":"Factory, Observer, Repository, etc."},
        {"id":"deployment",  "title":"Estrategia de deployment",    "description":"Docker, K8s, serverless, etc."},
        {"id":"testing",     "title":"Estrategia de testing",       "description":"Unit, integration, e2e, TDD"},
        {"id":"auth",        "title":"Autenticación y autorización", "description":"JWT, OAuth2, sessions, etc."},
        {"id":"api",         "title":"Diseño de API",               "description":"REST vs GraphQL vs gRPC"},
        {"id":"monitoring",  "title":"Monitorización y observabilidad","description":"OpenTelemetry, Prometheus, etc."},
    ]
    return JSONResponse(content={"templates": templates})
