"""
Roles/topics personalizados por especialista.
Permite al usuario asignar a cada IA un dominio específico que se inyecta
en su system prompt, haciéndola totalmente especializada en ese topic.
Se persiste en un JSON sencillo.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

# Ubicación del archivo de roles personalizados
_STORE_PATH = os.environ.get(
    "ANDROMEDA_CUSTOM_ROLES",
    str(Path(__file__).resolve().parents[3] / "config" / "custom_roles.json")
)


def _load() -> dict:
    try:
        with open(_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_role(specialist_id: str) -> dict | None:
    """Devuelve el rol personalizado de un especialista, o None."""
    return _load().get(specialist_id)


def set_role(specialist_id: str, topic: str, instructions: str = "") -> dict:
    """Asigna un topic + instrucciones personalizadas a un especialista."""
    data = _load()
    data[specialist_id] = {"topic": topic.strip(), "instructions": instructions.strip()}
    _save(data)
    return data[specialist_id]


def clear_role(specialist_id: str) -> None:
    """Elimina el rol personalizado de un especialista."""
    data = _load()
    data.pop(specialist_id, None)
    _save(data)


def all_roles() -> dict:
    return _load()


def build_specialization(topic: str, instructions: str = "") -> str:
    """Construye el bloque de especialización para inyectar en el system prompt."""
    if not topic:
        return ""
    block = f"""

ESPECIALIZACIÓN (PRIORITARIA):
Estás especializado exclusivamente en: {topic}.
Enfoca todas tus respuestas en este dominio. Si te preguntan algo
totalmente ajeno, ayuda igualmente pero relaciona tu respuesta con tu
especialidad cuando sea posible."""
    if instructions:
        block += f"\n\nINSTRUCCIONES ESPECÍFICAS:\n{instructions}"
    return block
