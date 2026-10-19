"""
slash_commands.py — Atajos de barra para el chat.

Inspirado en los slash commands de Claude Code: comandos cortos que el usuario
escribe al principio del mensaje y que se expanden a una instrucción completa
antes de llegar al modelo, o que ejecutan una acción de la app directamente.

Dos familias:
  • PROMPT: expanden a una instrucción ("/explica X" → prompt de explicación).
    El resto del mensaje se pasa como argumento.
  • ACTION: los interpreta el frontend/backend como una acción de la app
    (limpiar chat, listar skills…), no van al modelo.

Diseño deliberadamente declarativo: añadir un comando es añadir una entrada,
sin tocar la lógica de parseo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CMD_RE = re.compile(r"^/([a-zA-Z][\w-]*)\s*(.*)$", re.S)


@dataclass
class SlashCommand:
    name: str
    description: str
    kind: str                    # "prompt" | "action"
    template: str = ""           # para kind="prompt"; {args} se sustituye
    aliases: tuple[str, ...] = ()


COMMANDS: dict[str, SlashCommand] = {}


def _add(cmd: SlashCommand) -> None:
    COMMANDS[cmd.name] = cmd
    for a in cmd.aliases:
        COMMANDS[a] = cmd


# ── Comandos que expanden a un prompt ───────────────────────────────────────
_add(SlashCommand(
    "explain", "Explica un concepto desde cero, con un ejemplo concreto.",
    "prompt", aliases=("explica",),
    template=("Explica esto desde cero, empezando por la intuición y usando un ejemplo "
              "concreto antes de generalizar. No asumas conocimiento previo:\n\n{args}")))

_add(SlashCommand(
    "review", "Revisa código en busca de bugs, seguridad y estilo.",
    "prompt", aliases=("revisa",),
    template=("Revisa este código. Para cada hallazgo indica severidad, ubicación, por qué "
              "es un problema y una corrección concreta. Si está bien, dilo:\n\n{args}")))

_add(SlashCommand(
    "debug", "Diagnostica un error de forma sistemática.",
    "prompt", aliases=("depura",),
    template=("Ayúdame a depurar esto de forma sistemática: reproduce el problema, aísla la "
              "causa y propón un arreglo de la causa raíz, no del síntoma. Si te falta "
              "información, pídemela:\n\n{args}")))

_add(SlashCommand(
    "test", "Escribe tests para el código dado.",
    "prompt", aliases=("tests",),
    template=("Escribe tests para este código. Cubre el camino feliz, los casos límite y los "
              "errores esperados. Usa el framework de test idiomático del lenguaje:\n\n{args}")))

_add(SlashCommand(
    "refactor", "Reestructura código sin cambiar su comportamiento.",
    "prompt", aliases=("refactoriza",),
    template=("Refactoriza este código sin cambiar su comportamiento observable. Muestra el "
              "resultado completo y explica qué garantiza que el comportamiento no cambia:"
              "\n\n{args}")))

_add(SlashCommand(
    "summarize", "Resume un texto largo en sus puntos clave.",
    "prompt", aliases=("resume",),
    template=("Resume esto en sus puntos clave. Sé concreto: conserva cifras, nombres y "
              "conclusiones. Sin relleno:\n\n{args}")))

_add(SlashCommand(
    "translate", "Traduce un texto conservando el tono.",
    "prompt", aliases=("traduce",),
    template=("Traduce este texto conservando el tono y el registro original. Si hay términos "
              "técnicos con traducción discutible, mantén el original entre paréntesis:"
              "\n\n{args}")))

_add(SlashCommand(
    "improve", "Mejora la redacción de un texto.",
    "prompt", aliases=("mejora",),
    template=("Mejora la redacción de este texto: más claro y más directo, mismo significado. "
              "Devuelve solo el texto mejorado:\n\n{args}")))

_add(SlashCommand(
    "sql", "Escribe u optimiza una consulta SQL.",
    "prompt",
    template=("Ayúdame con este SQL. Si es optimización, di qué índices harían falta y qué "
              "cuestan. Muestra siempre la consulta completa resultante:\n\n{args}")))

_add(SlashCommand(
    "commit", "Redacta un mensaje de commit para unos cambios.",
    "prompt",
    template=("Redacta un mensaje de commit para estos cambios. Primera línea imperativa y "
              "bajo 72 caracteres; cuerpo explicando el porqué si hace falta:\n\n{args}")))

# ── Comandos que ejecuta la app (no van al modelo) ──────────────────────────
_add(SlashCommand("clear", "Vacía la conversación actual.", "action", aliases=("limpiar",)))
_add(SlashCommand("skills", "Muestra las skills disponibles.", "action"))
_add(SlashCommand("help", "Lista todos los comandos disponibles.", "action", aliases=("ayuda",)))


def parse(text: str) -> tuple[SlashCommand, str] | None:
    """Si el texto empieza por un comando conocido, devuelve (comando, argumentos)."""
    if not text or not text.lstrip().startswith("/"):
        return None
    m = _CMD_RE.match(text.strip())
    if not m:
        return None
    cmd = COMMANDS.get(m.group(1).lower())
    return (cmd, m.group(2).strip()) if cmd else None


def expand(text: str) -> str:
    """Expande un comando de tipo prompt. Si no aplica, devuelve el texto igual."""
    parsed = parse(text)
    if not parsed:
        return text
    cmd, args = parsed
    if cmd.kind != "prompt" or not args:
        return text
    return cmd.template.format(args=args)


def list_commands() -> list[dict]:
    """Lista de comandos únicos (sin alias duplicados), para la UI."""
    seen, out = set(), []
    for cmd in COMMANDS.values():
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        out.append({"name": cmd.name, "description": cmd.description,
                    "kind": cmd.kind, "aliases": list(cmd.aliases)})
    return sorted(out, key=lambda c: c["name"])
