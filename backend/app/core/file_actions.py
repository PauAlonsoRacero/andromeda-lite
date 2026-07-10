"""
Parser de acciones de archivo para modelos locales.

Los modelos pequeños no hacen "tool calling" estructurado de forma fiable, así
que Andromeda usa un protocolo simple y robusto basado en bloques de código:
la IA emite un bloque con una cabecera reconocible y el backend lo detecta,
lo ejecuta sobre el workspace y devuelve el resultado.

Formato que la IA debe emitir:

    ```andromeda:write path="notas/resumen.md"
    # Resumen
    contenido del archivo...
    ```

    ```andromeda:delete path="viejo.txt"
    ```

    ```andromeda:mkdir path="proyecto/src"
    ```

Acciones soportadas: write, mkdir, delete, move (move usa src/dst).

El parser es deliberadamente tolerante con el formato (comillas opcionales,
espacios) porque los modelos pequeños no son consistentes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.workspace import Workspace, WorkspaceError

# Cabecera del bloque. Tolerante con lo que los modelos locales generan en la
# práctica. Acepta TODAS estas variantes para la misma acción:
#   ```andromeda:write path="x"      (formato canónico)
#   ```write path="x"                 (sin prefijo andromeda:)
#   :write path="x"                   (sin fence, con dos puntos)  ← caso real visto
#   andromeda:write path="x"          (sin fence)
# El cuerpo va hasta el cierre ``` si hubo fence, o hasta el final / doble salto.
_ACTIONS = "write|append|edit|mkdir|delete|move|copy|read"

_BLOCK_RE = re.compile(
    r"```\s*(?:andromeda)?:?\s*(?P<action>" + _ACTIONS + r")"
    r"(?P<attrs>[^\n]*)\n"
    r"(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)

# Variante SIN fence de código: una línea que empieza por :write / andromeda:write
# / write seguida de path="...", y el cuerpo en las líneas siguientes hasta un
# fence de cierre, un nuevo bloque, o el final del texto.
_NOFENCE_RE = re.compile(
    r"^[ \t]*(?:andromeda)?:?[ \t]*(?P<action>" + _ACTIONS + r")\b"
    r"(?P<attrs>[^\n]*)\n"
    r"(?P<body>.*?)(?=\n```|\n[ \t]*(?:andromeda)?:?[ \t]*(?:" + _ACTIONS + r")\b|\Z)",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)

# Acciones que pueden venir en UNA sola línea (sin cuerpo): mkdir/delete/move/
# copy/read siempre; edit cuando trae find=/replace= en los atributos.
_ONELINE_RE = re.compile(
    r"^[ \t]*(?:andromeda)?:?[ \t]*(?P<action>mkdir|delete|move|copy|read|edit)\b"
    r"(?P<attrs>[^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)

# atributos tipo  key="value"  o  key=value
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"|(\w+)\s*=\s*(\S+)')


@dataclass
class FileAction:
    action: str
    attrs: dict
    body: str


@dataclass
class ActionResult:
    action: str
    ok: bool
    detail: str


def _parse_attrs(raw: str) -> dict:
    attrs: dict = {}
    for m in _ATTR_RE.finditer(raw or ""):
        if m.group(1) is not None:
            attrs[m.group(1).lower()] = m.group(2)
        else:
            attrs[m.group(3).lower()] = m.group(4)
    return attrs


def find_actions(text: str) -> list[FileAction]:
    """Extrae todas las acciones de archivo presentes en el texto del modelo.

    Primero busca bloques con fence (```...```), y si no encuentra ninguno,
    cae a la variante sin fence (:write path=...). Así toleramos los formatos
    que los modelos locales generan de verdad, no solo el canónico.
    """
    text = text or ""
    actions: list[FileAction] = []
    spans: list[tuple[int, int]] = []
    for m in _BLOCK_RE.finditer(text):
        actions.append(FileAction(
            action=m.group("action").lower(),
            attrs=_parse_attrs(m.group("attrs")),
            body=m.group("body"),
        ))
        spans.append((m.start(), m.end()))
    # Si no hubo bloques con fence, intentar la variante sin fence (con cuerpo).
    if not actions:
        for m in _NOFENCE_RE.finditer(text):
            body = m.group("body")
            body = re.sub(r"\n?```\s*$", "", body)
            actions.append(FileAction(
                action=m.group("action").lower(),
                attrs=_parse_attrs(m.group("attrs")),
                body=body,
            ))
            spans.append((m.start(), m.end()))
    # Acciones de una sola línea (mkdir/delete/move/copy/read) que pueden no
    # haber sido capturadas (no llevan cuerpo). Solo añadimos las que no solapen.
    for m in _ONELINE_RE.finditer(text):
        s = m.start()
        if any(s >= bs and s < be for bs, be in spans):
            continue  # ya cubierta por un bloque anterior
        attrs = _parse_attrs(m.group("attrs"))
        if "path" in attrs or "src" in attrs:
            actions.append(FileAction(
                action=m.group("action").lower(), attrs=attrs, body=""))
    return actions


def has_actions(text: str) -> bool:
    """True si el texto contiene al menos una acción de archivo (cualquier variante)."""
    return bool(find_actions(text))


def execute_actions(text: str, ws: Workspace | None = None) -> list[ActionResult]:
    """
    Detecta y ejecuta las acciones presentes en la respuesta del modelo.

    Devuelve una lista de resultados (uno por acción). El borrado se hace en
    modo reversible (papelera), nunca permanente desde el chat.
    """
    ws = ws or Workspace()
    results: list[ActionResult] = []

    for act in find_actions(text):
        try:
            if act.action == "write":
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                # quitar un posible salto final que añaden los modelos
                body = act.body
                if body.endswith("\n"):
                    body = body[:-1]
                # Si la extensión es .docx/.xlsx/.pdf, generar el binario real
                # (un .txt renombrado a .docx no abre en Word).
                from app.core.doc_builder import is_binary_doc, build_document
                if is_binary_doc(path):
                    try:
                        from app.core.workspace import _resolve_inside
                        abs_path = _resolve_inside(ws.root, path)
                        build_document(abs_path, body)
                        rel = str(abs_path.relative_to(ws.root)).replace("\\", "/")
                        results.append(ActionResult("write", True,
                                                    f"Documento creado: {rel}"))
                    except ImportError:
                        # Falta la librería → caer a texto plano, pero avisar
                        info = ws.write(path, body)
                        results.append(ActionResult("write", True,
                            f"Guardado como texto (falta librería para {path}): {info.path}"))
                    except Exception as de:
                        results.append(ActionResult("write", False,
                                                    f"Error creando documento {path}: {de}"))
                else:
                    info = ws.write(path, body)
                    results.append(ActionResult("write", True,
                                                f"Archivo guardado: {info.path}"))

            elif act.action == "mkdir":
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                info = ws.mkdir(path)
                results.append(ActionResult("mkdir", True,
                                            f"Carpeta creada: {info.path}"))

            elif act.action == "delete":
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                res = ws.delete(path, permanent=False)
                results.append(ActionResult("delete", True,
                                            f"Movido a papelera: {res['deleted']}"))

            elif act.action == "move":
                src = act.attrs.get("src")
                dst = act.attrs.get("dst")
                if not src or not dst:
                    raise WorkspaceError("faltan 'src' y/o 'dst'")
                info = ws.move(src, dst)
                results.append(ActionResult("move", True,
                                            f"Movido a: {info.path}"))

            elif act.action == "append":
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                body = act.body
                if body.endswith("\n"):
                    body = body[:-1]
                prev = ws.read(path) if ws.exists(path) else ""
                joined = (prev + ("\n" if prev and not prev.endswith("\n") else "") + body)
                info = ws.write(path, joined)
                results.append(ActionResult("append", True,
                                            f"Añadido a: {info.path}"))

            elif act.action == "edit":
                # Edición parcial: reemplaza un fragmento por otro sin reescribir
                # todo. Atributos: find="..." replace="..."  (o en el cuerpo,
                # separados por una línea '---' si el modelo lo pone así).
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                if not ws.exists(path):
                    raise WorkspaceError(f"no existe el archivo: {path}")
                find = act.attrs.get("find")
                replace = act.attrs.get("replace")
                # Permitir find/replace en el cuerpo: "buscar\n---\nreemplazar"
                if find is None and "\n---\n" in act.body:
                    find, replace = act.body.split("\n---\n", 1)
                    find = find.strip("\n")
                    replace = replace.rstrip("\n")
                if not find:
                    raise WorkspaceError("falta 'find' para editar")
                content = ws.read(path)
                if find not in content:
                    raise WorkspaceError(f"no se encontró el texto a reemplazar en {path}")
                n = content.count(find)
                new_content = content.replace(find, replace or "")
                info = ws.write(path, new_content)
                results.append(ActionResult("edit", True,
                                            f"Editado {info.path}: {n} reemplazo(s)"))

            elif act.action == "copy":
                src = act.attrs.get("src") or act.attrs.get("path")
                dst = act.attrs.get("dst")
                if not src or not dst:
                    raise WorkspaceError("faltan 'src' y/o 'dst'")
                if not ws.exists(src):
                    raise WorkspaceError(f"no existe el origen: {src}")
                content = ws.read(src)
                info = ws.write(dst, content)
                results.append(ActionResult("copy", True,
                                            f"Copiado a: {info.path}"))

            elif act.action == "read":
                # La IA pide leer un archivo. No modifica nada; el resultado se
                # adjunta para que la UI lo muestre (y queda en el contexto).
                path = act.attrs.get("path")
                if not path:
                    raise WorkspaceError("falta 'path'")
                if not ws.exists(path):
                    raise WorkspaceError(f"no existe el archivo: {path}")
                content = ws.read(path)
                preview = content[:500] + ("…" if len(content) > 500 else "")
                results.append(ActionResult("read", True,
                                            f"Leído {path} ({len(content)} car.): {preview}"))

        except WorkspaceError as e:
            results.append(ActionResult(act.action, False, str(e)))
        except Exception as e:  # noqa: BLE001 — robustez frente a entradas raras
            results.append(ActionResult(act.action, False, f"error: {e}"))

    return results


def strip_action_blocks(text: str) -> str:
    """Elimina los bloques de acción del texto para mostrar una respuesta limpia."""
    return _BLOCK_RE.sub("", text or "").strip()
