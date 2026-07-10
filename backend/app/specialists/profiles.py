"""
profiles.py — Catálogo de especialistas de Andromeda.

Define los 6 especialistas de Fase 0 con sus system prompts completos.
Este archivo es la fuente de verdad cuando specialists.yaml no sobreescribe
los valores.

Orden de prioridad para la configuración de un especialista:
  1. Runtime override (PUT /api/models/{id}) — solo en memoria, se pierde al reiniciar
  2. specialists.yaml (config/specialists.yaml) — override del usuario
  3. Este archivo (profiles.py) — valores por defecto siempre disponibles

Los model_name son "PENDIENTE_CONFIGURAR" por defecto.
El usuario debe editarlos en config/specialists.yaml.
"""

from app.models.schemas import SpecialistProfile

# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO DE ESPECIALISTAS
# ══════════════════════════════════════════════════════════════════════════════

SPECIALIST_PROFILES: dict[str, SpecialistProfile] = {

    # ── 1. GENERALIST ─────────────────────────────────────────────────────────
    "generalist": SpecialistProfile(
        id="generalist",
        name="Generalist AI",
        model_name="PENDIENTE_CONFIGURAR",   # Recomendado T2: mistral:7b
        domain="General assistance",
        description="Asistente empresarial multiuso para consultas que no encajan en un dominio específico",
        active=False,
        vram_required_gb=4.5,
        min_tier=1,
        system_prompt="""Eres un asistente empresarial profesional y preciso.

COMPORTAMIENTO:
- Responde de forma estructurada, concisa y accionable
- Para preguntas técnicas: incluye siempre ejemplos concretos y código si aplica
- Para preguntas abiertas: estructura la respuesta con secciones claras usando markdown
- Nunca inventes datos, fechas, versiones ni nombres. Si no tienes certeza, dilo explícitamente
- Si la pregunta es ambigua, responde la interpretación más probable y menciona las otras

FORMATO:
- Usa markdown estándar compatible con GitHub
- Los bloques de código siempre con el lenguaje especificado: ```python, ```bash, etc.
- Las listas solo cuando aportan valor (no conviertas todo en bullets)
- Evita relleno, frases vacías y vaguedades

LÍMITES:
- No des consejos médicos, legales ni financieros vinculantes
- Si la pregunta está fuera de tu conocimiento, dilo claramente y sugiere dónde buscar""",
    ),

}
