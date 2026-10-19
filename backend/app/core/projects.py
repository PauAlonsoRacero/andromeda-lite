"""
projects.py — Archivos y contexto de cada proyecto.

Antes los proyectos eran solo una pantalla: sus instrucciones y su memoria se
guardaban en el navegador y nunca llegaban al modelo, y "nueva conversación"
descartaba el id del proyecto.

Ahora cada proyecto tiene una carpeta en disco con los archivos y carpetas que
el usuario añade. En una conversación del proyecto:
  • las instrucciones del proyecto van al modelo en cada mensaje;
  • el modelo ve el árbol de archivos y el contenido de los más relevantes;
  • la carpeta del proyecto es el espacio de trabajo: lo que el modelo crea o
    modifica queda dentro del proyecto, no en la carpeta general.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("andromeda.projects")

_ID_OK = re.compile(r"^[A-Za-z0-9-]{6,64}$")
_MAX_FILE_BYTES = 10 * 1024 * 1024          # 10 MB por archivo
_MAX_PROJECT_FILES = 2000
# Extensiones cuyo contenido se lee como texto para dárselo al modelo.
_TEXT_EXTS = {".txt", ".md", ".markdown", ".html", ".htm", ".css", ".js", ".jsx", ".ts",
              ".tsx", ".json", ".py", ".csv", ".xml", ".yaml", ".yml", ".toml", ".ini",
              ".sh", ".sql", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".php", ".rb",
              ".vue", ".svelte", ".env.example", ".log", ".tex", ".rst"}
# Carpetas que nunca aportan y pueden tener miles de archivos.
_IGNORAR = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build",
            ".next", ".cache", ".idea", ".vscode"}


class ProjectError(ValueError):
    pass


def _data_dir() -> Path:
    base = os.environ.get("ANDROMEDA_DATA_DIR")
    if base:
        return Path(base)
    db = os.environ.get("ANDROMEDA_MEMORY_DB_PATH")
    return Path(db).parent if db else Path("data")


def project_root(project_id: str, *, create: bool = False) -> Path:
    if not project_id or not _ID_OK.match(project_id):
        raise ProjectError("id de proyecto no válido")
    root = _data_dir() / "projects" / project_id / "files"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _inside(root: Path, rel: str) -> Path:
    """Ruta dentro del proyecto; rechaza '..' y rutas absolutas."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or any(p in ("..", "") for p in rel.split("/")):
        raise ProjectError("ruta no válida")
    destino = (root / rel).resolve()
    if root.resolve() not in destino.parents and destino != root.resolve():
        raise ProjectError("ruta fuera del proyecto")
    return destino


def _ignorada(rel: str) -> bool:
    return any(parte in _IGNORAR for parte in rel.split("/"))


def list_files(project_id: str) -> list[dict]:
    root = project_root(project_id)
    if not root.exists():
        return []
    salida = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if not _ignorada(rel):
                salida.append({"path": rel, "size": p.stat().st_size})
    return salida


def save_file(project_id: str, rel: str, data: bytes) -> dict:
    if _ignorada(rel):
        return {"path": rel, "skipped": "ignored"}
    if len(data) > _MAX_FILE_BYTES:
        raise ProjectError(f"archivo demasiado grande (máx. {_MAX_FILE_BYTES // 1024 // 1024} MB)")
    root = project_root(project_id, create=True)
    if len(list_files(project_id)) >= _MAX_PROJECT_FILES:
        raise ProjectError("el proyecto ya tiene demasiados archivos")
    destino = _inside(root, rel)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(data)
    return {"path": destino.relative_to(root).as_posix(), "size": len(data)}


def delete_path(project_id: str, rel: str) -> bool:
    root = project_root(project_id)
    destino = _inside(root, rel)
    if destino.is_file():
        destino.unlink()
        return True
    if destino.is_dir():
        import shutil
        shutil.rmtree(destino)
        return True
    return False


def read_text(project_id: str, rel: str, limite: int = 200_000) -> str:
    destino = _inside(project_root(project_id), rel)
    return destino.read_bytes()[:limite].decode("utf-8", "replace")


def _es_texto(rel: str) -> bool:
    return Path(rel).suffix.lower() in _TEXT_EXTS or Path(rel).name.lower() in {
        "dockerfile", "makefile", "readme", "license"}


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúñü0-9_]{3,}", (texto or "").lower()))


def build_context(project_id: str, name: str, instructions: str, prompt: str,
                  max_chars: int = 14_000) -> str:
    """Bloque de contexto del proyecto para el prompt.

    Incluye las instrucciones, el árbol de archivos y el contenido de los más
    relevantes para el mensaje. Si el proyecto es pequeño, entra entero.
    """
    partes = [f"PROYECTO ACTIVO: {name or project_id}"]
    if (instructions or "").strip():
        partes.append(f"INSTRUCCIONES DEL PROYECTO (síguelas siempre):\n{instructions.strip()}")

    archivos = list_files(project_id)
    if not archivos:
        return "\n\n".join(partes)

    arbol = "\n".join(f"- {a['path']} ({a['size']} B)" for a in archivos[:200])
    if len(archivos) > 200:
        arbol += f"\n… y {len(archivos) - 200} archivos más"
    partes.append(
        "ARCHIVOS DEL PROYECTO (esta carpeta es tu espacio de trabajo: para crear o "
        "modificar un archivo emite andromeda:write con su ruta relativa y el contenido "
        f"completo):\n{arbol}")

    textos = [a for a in archivos if _es_texto(a["path"]) and a["size"] <= 400_000]
    total = sum(a["size"] for a in textos)
    claves = _palabras(prompt)

    # Cada archivo se lee UNA vez por mensaje (antes dos: al puntuar y al
    # incluirlo). En proyectos grandes solo se puntúan los 300 primeros por
    # nombre coincidente, para no leer miles de archivos en cada pregunta.
    cache: dict[str, str] = {}

    def texto_de(ruta: str) -> str:
        if ruta not in cache:
            try:
                cache[ruta] = read_text(project_id, ruta)
            except OSError:
                cache[ruta] = ""
        return cache[ruta]

    def puntos(a):
        nombre = a["path"].lower()
        return 5 * sum(1 for w in claves if w in nombre) + len(claves & _palabras(texto_de(a["path"])[:50_000]))

    if total <= max_chars:
        elegidos = textos
    else:
        candidatos = sorted(textos, key=lambda a: -sum(1 for w in claves if w in a["path"].lower()))[:300]
        elegidos = sorted(candidatos, key=puntos, reverse=True)
    usado = 0
    for a in elegidos:
        if usado >= max_chars:
            break
        contenido = texto_de(a["path"])
        if not contenido:
            continue
        trozo = contenido[: max_chars - usado]
        partes.append(f"--- contenido de «{a['path']}» ---\n{trozo}\n--- fin ---")
        usado += len(trozo)
    return "\n\n".join(partes)
