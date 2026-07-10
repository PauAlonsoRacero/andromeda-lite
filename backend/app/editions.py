"""
editions.py — Ediciones de Andromeda (Lite / Pro) y feature gating.

Andromeda se distribuye en dos ediciones que comparten el mismo núcleo:

  • LITE  — Gratis, open source (MIT). Producto completo para uso individual
            y 100% local. Es la edición por defecto. Sin recorte del motor de
            orquestación: todo lo que corre en tu máquina está disponible.

  • PRO   — Edición comercial para equipos y empresas. Añade una capa de
            colaboración/operación (multiusuario, control de acceso,
            observabilidad de equipo, white-label) y da derecho a soporte y
            consultoría. No capa el motor: amplía el producto hacia el uso
            organizativo.

La edición activa se resuelve, por orden de prioridad:
  1. Variable de entorno  ANDROMEDA_EDITION = lite | pro
  2. Archivo de licencia   (ANDROMEDA_LICENSE_FILE, JSON con {"edition": "pro", ...})
  3. Por defecto: "lite"

Diseño honesto: este módulo define QUÉ ofrece cada edición y resuelve cuál está
activa. La validación criptográfica de licencias y la pasarela de pago son la
siguiente capa (backend de facturación) y NO se simulan aquí: si no hay licencia
Pro válida presente, la edición es Lite. Activar Pro a mano por env var sirve
para desarrollo, demos y despliegues self-hosted con contrato.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List


LITE = "lite"
PRO = "pro"


# ── Catálogo de features ────────────────────────────────────────────────────
# Cada feature tiene una clave estable (la usa el frontend para gatear UI),
# una etiqueta legible y la lista de ediciones donde está disponible.
@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    editions: tuple
    description: str = ""

    def available_in(self, edition: str) -> bool:
        return edition in self.editions


# El núcleo (orquestación multi-IA, chat, especialistas, MLOps local, privacidad)
# está en AMBAS ediciones: Lite es un producto completo, no una demo.
FEATURES: List[Feature] = [
    # ── Andromeda Lite (gratis, open source) ──
    Feature("local_inference", "Inferencia 100% local", (LITE, PRO),
            "Una IA local que escala su potencia según tu prompt y tu hardware. Nada sale de tu máquina."),
    Feature("file_actions", "Lectura y escritura de archivos", (LITE, PRO),
            "Crea, edita y borra archivos reales (docx, xlsx, pdf, md)."),
    Feature("mcp_tools", "Herramientas MCP", (LITE, PRO),
            "Conecta la IA a archivos, web, memoria, terminal y más vía servidores MCP."),
    Feature("codex", "Codex (ejecución de código)", (LITE, PRO),
            "Editor con ejecución en sandbox para múltiples lenguajes."),
    Feature("incognito", "Modo incógnito", (LITE, PRO),
            "Sesión sin historial ni rastro, con interfaz noir."),

    # ── Andromeda Pro (ampliación de pago) ──
    Feature("orchestration_multi", "Orquestación multi-IA (paralelo + fusión)", (PRO,),
            "Varios especialistas trabajando en paralelo y una respuesta fusionada. El corazón de Pro."),
    Feature("smart_routing", "Routing inteligente de especialistas", (PRO,),
            "Un clasificador decide qué especialistas activar para cada prompt."),
    Feature("mlops_local", "MLOps y estadísticas avanzadas", (PRO,),
            "Métricas, percentiles, drift y proyecciones."),
    Feature("fine_tuning", "Fine-tuning y Laboratorio de IA", (PRO,),
            "Ajuste y entrenamiento de modelos en tu máquina."),
    Feature("multi_user", "Multiusuario y cuentas", (PRO,),
            "Gestión de usuarios, sesiones y control de acceso por roles."),
    Feature("team_observability", "Observabilidad de equipo", (PRO,),
            "Telemetría agregada de todo el equipo, no solo local."),
    Feature("priority_support", "Soporte prioritario y consultoría", (PRO,),
            "Canal de soporte con SLA y acompañamiento en el despliegue."),
    Feature("white_label", "White-label / branding", (PRO,),
            "Personalizar nombre, logo y colores para tu organización."),
]

FEATURES_BY_KEY: Dict[str, Feature] = {f.key: f for f in FEATURES}


@dataclass
class EditionInfo:
    edition: str
    label: str
    is_pro: bool
    features: Dict[str, bool] = field(default_factory=dict)
    license_holder: str | None = None
    license_valid: bool = False


def _read_license() -> dict:
    """Lee el archivo de licencia si existe. Formato JSON:
        {"edition": "pro", "holder": "ACME S.L.", "expires": "2027-01-01"}
    Sin validación criptográfica todavía (capa futura): la presencia de un
    archivo bien formado con edition=pro habilita Pro en self-hosted."""
    path = os.environ.get("ANDROMEDA_LICENSE_FILE", "").strip()
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def resolve_edition() -> str:
    """Edicion fijada a LITE en el paquete Lite (sin codigo Pro)."""
    return LITE


def get_edition_info() -> EditionInfo:
    """Información completa de la edición activa + mapa de features."""
    edition = resolve_edition()
    is_pro = edition == PRO
    lic = _read_license()
    feature_map = {f.key: f.available_in(edition) for f in FEATURES}
    return EditionInfo(
        edition=edition,
        label="Andromeda Pro" if is_pro else "Andromeda Lite",
        is_pro=is_pro,
        features=feature_map,
        license_holder=lic.get("holder") if is_pro else None,
        license_valid=bool(lic) if is_pro else False,
    )


def feature_enabled(key: str) -> bool:
    """Helper para el backend: ¿está la feature activa en la edición actual?"""
    info = get_edition_info()
    return info.features.get(key, False)


def orchestration_enabled() -> bool:
    """¿Está disponible la orquestación multi-IA (routing + paralelo + fusión)?

    Es la línea que separa Lite de Pro:
      • Lite → False: orquestación lineal de UNA sola IA (con power-scaling
        de nivel según prompt y hardware). Sin clasificador multi-especialista
        ni fusión de varias respuestas.
      • Pro  → True: pipeline completo multi-IA.

    En la edición Lite los módulos `classifier`/`merger` multi y `orchestrator`
    complejo ni siquiera se distribuyen; este guard evita además que cualquier
    camino los invoque."""
    return feature_enabled("orchestration_multi")


def catalog() -> List[dict]:
    """Catálogo de features para mostrar comparativa Lite vs Pro en la UI."""
    return [
        {
            "key": f.key,
            "label": f.label,
            "description": f.description,
            "lite": f.available_in(LITE),
            "pro": f.available_in(PRO),
        }
        for f in FEATURES
    ]
