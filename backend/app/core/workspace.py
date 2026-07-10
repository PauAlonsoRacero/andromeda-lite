"""
Andromeda Workspace — acceso seguro al sistema de archivos.

Permite que Andromeda cree, lea, modifique y borre archivos en local, como
hace Claude, PERO con un perímetro de seguridad estricto:

  • Todas las operaciones quedan confinadas a un directorio raíz (workspace).
  • Imposible escapar del workspace con "..", rutas absolutas o symlinks.
  • El borrado es reversible por defecto (mueve a una papelera interna).
  • Cada operación se valida antes de tocar el disco.

El workspace por defecto es ~/Andromeda_Files, pero se puede cambiar con la
variable de entorno ANDROMEDA_WORKSPACE (p. ej. apuntar a ~/Documents).

Como Andromeda es local-first, el usuario opera sobre SUS propios archivos en
SU máquina; el perímetro existe para que un error del modelo (o un prompt
malicioso inyectado vía web) no pueda tocar nada fuera del workspace elegido.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path


class WorkspaceError(Exception):
    """Error de operación de workspace (ruta inválida, fuera de límites, etc)."""


# Límites defensivos
_MAX_FILE_BYTES = 25 * 1024 * 1024      # 25 MB por archivo
_MAX_LIST_ENTRIES = 5000                # techo al listar
_TRASH_DIRNAME = ".andromeda_trash"     # papelera interna (oculta)


def _default_workspace() -> Path:
    """Carpeta de trabajo por defecto, en un sitio VISIBLE para el usuario.

    Preferimos ~/Desktop/Andromeda (o ~/Escritorio/Andromeda en sistemas en
    español) para que los archivos que crea la IA aparezcan donde el usuario
    los ve, no en una carpeta escondida. Si no hay Escritorio, caemos a
    ~/Andromeda_Files.
    """
    home = Path.home()
    for desktop_name in ("Desktop", "Escritorio"):
        desktop = home / desktop_name
        if desktop.is_dir():
            return desktop / "Andromeda"
    return home / "Andromeda_Files"


def get_workspace_root() -> Path:
    """Directorio raíz del workspace. Configurable vía ANDROMEDA_WORKSPACE."""
    env = os.getenv("ANDROMEDA_WORKSPACE")
    root = Path(env).expanduser() if env else _default_workspace()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_inside(root: Path, rel_path: str) -> Path:
    """
    Resuelve `rel_path` dentro de `root` y garantiza que NO escapa.

    Lanza WorkspaceError si la ruta intenta salirse (vía "..", ruta absoluta,
    o symlink que apunte fuera). Esta es la única puerta por la que pasan
    todas las operaciones, así que la seguridad vive aquí.
    """
    if rel_path is None:
        raise WorkspaceError("ruta vacía")

    raw = str(rel_path).strip().replace("\\", "/")

    # Rechazar rutas absolutas ANTES de normalizar (Unix "/x" y Windows "C:/x")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise WorkspaceError("rutas absolutas no permitidas")

    # Rechazar cualquier componente ".." de forma explícita (defensa en capas)
    parts = [seg for seg in raw.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise WorkspaceError("ruta con '..' no permitida")

    cleaned = "/".join(parts)
    if not cleaned:
        raise WorkspaceError("ruta vacía o raíz no permitida")

    candidate = (root / cleaned).resolve()

    # El candidato resuelto debe estar dentro de root (cubre symlinks, etc.)
    if candidate != root and root not in candidate.parents:
        raise WorkspaceError("ruta fuera del workspace")

    # Nunca dejar tocar la papelera interna directamente
    trash = (root / _TRASH_DIRNAME).resolve()
    if candidate == trash or trash in candidate.parents:
        raise WorkspaceError("ruta reservada")

    return candidate


@dataclass
class FileInfo:
    path: str
    is_dir: bool
    size: int = 0
    modified: float = 0.0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "modified": self.modified,
        }


@dataclass
class Workspace:
    """Fachada de operaciones de archivos confinadas a un directorio raíz."""

    root: Path = field(default_factory=get_workspace_root)

    def __post_init__(self):
        # Aceptar tanto str como Path: normalizamos siempre a Path para que las
        # operaciones con '/' funcionen aunque se construya con una cadena.
        if not isinstance(self.root, Path):
            self.root = Path(self.root)

    # ── lectura ──────────────────────────────────────────────────────────────
    def list(self, subpath: str = "") -> list[FileInfo]:
        """Lista archivos y carpetas (recursivo) bajo subpath."""
        base = self.root if not subpath else _resolve_inside(self.root, subpath)
        if not base.exists():
            raise WorkspaceError(f"no existe: {subpath}")

        out: list[FileInfo] = []
        for p in sorted(base.rglob("*")):
            # Saltar la papelera interna
            if _TRASH_DIRNAME in p.parts:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            out.append(FileInfo(
                path=str(p.relative_to(self.root)).replace("\\", "/"),
                is_dir=p.is_dir(),
                size=st.st_size if p.is_file() else 0,
                modified=st.st_mtime,
            ))
            if len(out) >= _MAX_LIST_ENTRIES:
                break
        return out

    def read(self, rel_path: str) -> str:
        """Lee un archivo de texto."""
        p = _resolve_inside(self.root, rel_path)
        if not p.exists() or not p.is_file():
            raise WorkspaceError(f"no existe el archivo: {rel_path}")
        if p.stat().st_size > _MAX_FILE_BYTES:
            raise WorkspaceError("archivo demasiado grande para leer")
        try:
            return p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise WorkspaceError("el archivo no es texto UTF-8")

    def exists(self, rel_path: str) -> bool:
        try:
            return _resolve_inside(self.root, rel_path).exists()
        except WorkspaceError:
            return False

    def context_block(self, max_files: int = 20, inline_text_files: int = 3) -> str:
        """Genera un bloque de contexto con los archivos del workspace.

        Lista los archivos existentes (para que la IA sepa qué hay y pueda
        MODIFICARLOS por nombre en vez de crear duplicados) e incluye el
        contenido completo de los archivos de texto más recientes, para que
        "mejora el index.html" funcione sin pedirle el código al usuario.
        """
        try:
            items = [f for f in self.list() if not f.is_dir]
        except WorkspaceError:
            return ""
        if not items:
            return ""
        # Más recientes primero
        items.sort(key=lambda f: f.modified, reverse=True)
        names = [f.path for f in items[:max_files]]
        block = ["ARCHIVOS EN TU ESPACIO DE TRABAJO (puedes leerlos y MODIFICARLOS "
                 "por su nombre; para editar uno, vuelve a emitir andromeda:write con "
                 "el MISMO path y el contenido completo ya modificado):"]
        block.append(", ".join(names))
        # Incluir contenido de los archivos de texto más recientes
        text_exts = (".html", ".htm", ".txt", ".md", ".css", ".js", ".json",
                     ".py", ".csv", ".xml", ".yaml", ".yml")
        shown = 0
        for f in items:
            if shown >= inline_text_files:
                break
            if f.path.lower().endswith(text_exts) and f.size <= 20000:
                try:
                    content = self.read(f.path)
                except WorkspaceError:
                    continue
                block.append(f"\n--- contenido de «{f.path}» ---\n{content}\n--- fin ---")
                shown += 1
        return "\n".join(block)

    # ── escritura ─────────────────────────────────────────────────────────────
    def write(self, rel_path: str, content: str, *, overwrite: bool = True) -> FileInfo:
        """Crea o sobrescribe un archivo de texto. Crea carpetas intermedias."""
        if content is None:
            content = ""
        data = content.encode("utf-8")
        if len(data) > _MAX_FILE_BYTES:
            raise WorkspaceError("contenido demasiado grande")

        p = _resolve_inside(self.root, rel_path)
        if p.exists() and p.is_dir():
            raise WorkspaceError("la ruta es una carpeta, no un archivo")
        if p.exists() and not overwrite:
            raise WorkspaceError("el archivo ya existe (overwrite=false)")

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        st = p.stat()
        return FileInfo(
            path=str(p.relative_to(self.root)).replace("\\", "/"),
            is_dir=False, size=st.st_size, modified=st.st_mtime,
        )

    def mkdir(self, rel_path: str) -> FileInfo:
        """Crea una carpeta (y las intermedias)."""
        p = _resolve_inside(self.root, rel_path)
        p.mkdir(parents=True, exist_ok=True)
        return FileInfo(path=str(p.relative_to(self.root)).replace("\\", "/"),
                        is_dir=True, modified=p.stat().st_mtime)

    def move(self, src: str, dst: str) -> FileInfo:
        """Mueve/renombra un archivo o carpeta dentro del workspace."""
        ps = _resolve_inside(self.root, src)
        pd = _resolve_inside(self.root, dst)
        if not ps.exists():
            raise WorkspaceError(f"no existe el origen: {src}")
        pd.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ps), str(pd))
        is_dir = pd.is_dir()
        return FileInfo(path=str(pd.relative_to(self.root)).replace("\\", "/"),
                        is_dir=is_dir,
                        size=pd.stat().st_size if pd.is_file() else 0,
                        modified=pd.stat().st_mtime)

    # ── borrado (reversible por defecto) ───────────────────────────────────────
    def delete(self, rel_path: str, *, permanent: bool = False) -> dict:
        """
        Borra un archivo o carpeta.

        Por defecto NO es destructivo: mueve el elemento a una papelera interna
        (.andromeda_trash) de la que se puede restaurar. Con permanent=True se
        elimina de verdad (irreversible).
        """
        p = _resolve_inside(self.root, rel_path)
        if not p.exists():
            raise WorkspaceError(f"no existe: {rel_path}")

        if permanent:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return {"deleted": rel_path, "permanent": True}

        # Papelera: conserva la ruta relativa completa + timestamp.
        # Codificamos los separadores como '~' para guardar todo en un nombre
        # plano y poder restaurar a la ubicación original.
        trash = self.root / _TRASH_DIRNAME
        trash.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        rel = str(p.relative_to(self.root)).replace("\\", "/")
        safe_name = rel.replace("/", "~")
        target = trash / f"{stamp}__{safe_name}"
        shutil.move(str(p), str(target))
        return {"deleted": rel_path, "permanent": False,
                "trash_id": target.name}

    def restore(self, trash_id: str, dest: str | None = None) -> FileInfo:
        """Restaura un elemento de la papelera."""
        if "/" in trash_id or "\\" in trash_id or ".." in trash_id:
            raise WorkspaceError("trash_id inválido")
        src = (self.root / _TRASH_DIRNAME / trash_id)
        if not src.exists():
            raise WorkspaceError("no existe en la papelera")
        # nombre original tras el doble guion bajo; '~' vuelve a ser '/'
        encoded = trash_id.split("__", 1)[1] if "__" in trash_id else trash_id
        original = encoded.replace("~", "/")
        pd = _resolve_inside(self.root, dest or original)
        pd.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(pd))
        return FileInfo(path=str(pd.relative_to(self.root)).replace("\\", "/"),
                        is_dir=pd.is_dir(),
                        size=pd.stat().st_size if pd.is_file() else 0,
                        modified=pd.stat().st_mtime)
