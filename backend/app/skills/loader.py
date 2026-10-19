"""
skills/loader.py — Andromeda Skills (paquetes de capacidad reutilizables).

Inspirado en Claude Agent Skills (Anthropic, oct. 2025): una skill es una
carpeta con un SKILL.md (frontmatter YAML + instrucciones) que el sistema
descubre automáticamente por su descripción, sin que el usuario tenga que
seleccionarla a mano. Solo el nombre y la descripción de cada skill viven en
memoria; el cuerpo completo se inyecta en el prompt únicamente cuando la
tarea coincide con esa skill.

Reutiliza el mismo motor BM25 del RAG (app/rag/bm25.py) para el matching por
descripción: no es nueva infraestructura, es el mismo índice aplicado a otro
tipo de documento. Cero dependencias nuevas, funciona 100% offline.

Formato de config/skills/<nombre>/SKILL.md:
    ---
    name: code-review
    description: Revisa cambios de código en busca de bugs, seguridad y estilo.
    specialists: [software-engineering, verifier]
    ---
    <instrucciones en markdown que se inyectan cuando la skill activa>
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.rag.bm25 import BM25Index

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)
_MIN_TERM_OVERLAP = 2       # términos del prompt que deben aparecer en la skill
_MIN_MARGIN_RATIO = 1.35    # margen del primero sobre el segundo cuando empatan

_MIN_CONTENT_TERMS = 3      # términos con contenido mínimos para considerar una skill
_STEM_LEN = 6               # longitud de raíz para tolerar plurales y conjugaciones

# Palabras vacías ES/EN: sin filtrarlas, cualquier frase hace match con cualquier
# skill por coincidencias de "de", "que", "the", "is"...
_STOPWORDS = frozenset("""
de la que el en y a los del se las por un para con no una su al lo como mas pero sus
le ya o este si porque esta entre cuando muy sin sobre tambien me hasta hay donde quien
desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto mi antes
algunos qué unos yo otro otras otra él tanto esa estos mucho quienes nada muchos cual sea
poco ella estar haber estas estaba estamos algunas algo nosotros mi tu te ti tus ellas
nosotras vosotros vosotras os mio mia tuyo suyo nuestro vuestro esos esas
the of and to in is it you that he was for on are as with his they i at be this have from
or one had by word but not what all were we when your can said there use an each which she
do how their if will up other about out many then them these so some her would make like
him into time has look two more write go see number no way could people my than first been
call who oil its now find long down day did get come made may part
esto esta este ese esa aquel cual cuales cuyo cuya donde cuando como porque
""".split())


def _stem(word: str) -> str:
    """Raíz aproximada por truncado.

    El español flexiona mucho ("redacta"/"redactar"/"redactando",
    "correo"/"correos"). Un stemmer completo sería otra dependencia; truncar a
    los primeros caracteres captura casi toda la variación con coste cero y
    es predecible, que aquí importa más que la precisión lingüística.
    """
    return word[:_STEM_LEN] if len(word) > _STEM_LEN else word


def _stems(words) -> set:
    return {_stem(w) for w in words}


@dataclass
class Skill:
    id: str
    name: str
    description: str
    specialists: list[str] = field(default_factory=list)
    triggers: str = ""
    user_created: bool = False
    body: str = ""
    path: str = ""


def _parse_skill_md(path: Path) -> Skill | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FRONTMATTER.match(raw)
    if not m:
        return None
    fm_text, body = m.group(1), m.group(2).strip()
    meta: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    specialists = []
    if meta.get("specialists"):
        specialists = [s.strip() for s in meta["specialists"].strip("[]").split(",") if s.strip()]
    return Skill(
        id=path.parent.name,
        name=meta.get("name", path.parent.name),
        description=meta.get("description", ""),
        specialists=specialists,
        triggers=meta.get("triggers", ""),
        body=body,
        path=str(path),
    )


class SkillRegistry:
    """Descubre skills en disco e indexa sus descripciones para matching automático."""

    def __init__(self, skills_dir: str | Path, user_skills_dir: str | Path | None = None):
        self.skills_dir = Path(skills_dir)
        # Las skills del usuario viven aparte (en el directorio de datos) para
        # que actualizar la app no las pise nunca.
        self.user_skills_dir = Path(user_skills_dir) if user_skills_dir else None
        self._lock = threading.Lock()
        self.skills: dict[str, Skill] = {}
        self._index: BM25Index | None = None
        self.reload()

    def reload(self) -> int:
        """Reescanea el directorio de skills. Devuelve nº de skills cargadas."""
        with self._lock:
            self.skills = {}
            # Orden: primero las de fábrica, luego las del usuario (que tienen
            # prioridad si comparten id).
            for base, is_user in ((self.skills_dir, False), (self.user_skills_dir, True)):
                if not base or not base.exists():
                    continue
                for sub in sorted(base.iterdir()):
                    md = sub / "SKILL.md"
                    if sub.is_dir() and md.exists():
                        skill = _parse_skill_md(md)
                        if skill and skill.description:
                            skill.user_created = is_user
                            self.skills[skill.id] = skill
            # Índice BM25 solo sobre las descripciones (en memoria, no persistido:
            # las skills viven en disco y se recargan al arrancar / bajo demanda).
            idx = BM25Index(self.skills_dir / ".skills_index.json")
            idx.chunks, idx.df = [], idx.df.__class__()
            for sid, sk in self.skills.items():
                # Se indexa nombre + descripción + cuerpo: la descripción sola es
                # demasiado corta para que BM25 discrimine bien entre 9+ skills.
                # La descripción pesa el triple por ser la señal más intencional.
                # 'triggers' son los términos que la gente usa de verdad al pedir esto;
                # pesan alto porque son la señal de intención más directa.
                doc = (f"{sk.name} {sk.description} {sk.description} "
                       f"{sk.triggers} {sk.triggers} {sk.triggers} {sk.body}")
                idx.add_document(sid, doc, meta={"name": sk.name})
            self._index = idx
            return len(self.skills)

    def match(self, prompt: str, k: int = 1) -> list[Skill]:
        """Skills cuya descripción encaja claramente con el prompt.

        No basta el score BM25 crudo: su escala depende del tamaño del índice
        (con pocas skills el IDF se desploma y nada supera un umbral fijo). El
        criterio decisivo es cuántos términos con contenido del prompt aparecen
        de verdad en la skill; BM25 solo decide el orden entre las candidatas.

        Ante la duda no se activa nada: inyectar la instrucción equivocada es
        peor que no inyectar ninguna.
        """
        if not self.skills or self._index is None:
            return []
        from app.rag.bm25 import _normalize
        terms = [w for w in _normalize(prompt) if w not in _STOPWORDS]
        # Un prompt con poca sustancia (saludos, "gracias") nunca necesita skill.
        if len(terms) < _MIN_CONTENT_TERMS:
            return []

        hits = self._index.query(" ".join(terms), k=max(k, 2))
        if not hits:
            return []

        # Solapamiento real de términos con cada candidata.
        term_set = _stems(terms)
        scored = []
        for h in hits:
            sk = self.skills.get(h["doc_id"])
            if not sk:
                continue
            doc_terms = _stems(_normalize(f"{sk.name} {sk.description} {sk.triggers}"))
            overlap = len(term_set & doc_terms)
            if overlap >= _MIN_TERM_OVERLAP:
                scored.append((overlap, h["score"], sk))
        if not scored:
            return []

        # Orden: primero por solapamiento, luego por score BM25.
        scored.sort(key=lambda x: (-x[0], -x[1]))
        # Si la primera y la segunda empatan en solapamiento y score similar, la
        # señal no es concluyente.
        if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[1][1] > 0:
            if scored[0][1] / scored[1][1] < _MIN_MARGIN_RATIO:
                return []
        return [sk for _, _, sk in scored[:k]]

    def list_skills(self) -> list[dict]:
        return [{"id": s.id, "name": s.name, "description": s.description,
                 "specialists": s.specialists, "triggers": s.triggers,
                 "user_created": s.user_created} for s in self.skills.values()]

    def get(self, skill_id: str) -> Skill | None:
        return self.skills.get(skill_id)

    # ── Skills creadas por el usuario ───────────────────────────────────────

    def save_user_skill(self, skill_id: str, name: str, description: str,
                        body: str, triggers: str = "") -> Skill:
        """Crea o actualiza una skill del usuario en disco y recarga el índice."""
        if self.user_skills_dir is None:
            raise RuntimeError("No hay directorio de skills de usuario configurado")
        safe_id = re.sub(r"[^a-z0-9_-]", "-", (skill_id or "").strip().lower()).strip("-")
        if not safe_id:
            raise ValueError("Identificador de skill inválido")
        if not description.strip():
            raise ValueError("La descripción es obligatoria: es lo que decide cuándo se activa")
        folder = self.user_skills_dir / safe_id
        folder.mkdir(parents=True, exist_ok=True)
        front = [f"name: {name or safe_id}", f"description: {description.strip()}"]
        if triggers.strip():
            front.append(f"triggers: {triggers.strip()}")
        (folder / "SKILL.md").write_text(
            "---\n" + "\n".join(front) + "\n---\n" + (body or "").strip() + "\n",
            encoding="utf-8")
        self.reload()
        return self.skills[safe_id]

    def delete_user_skill(self, skill_id: str) -> bool:
        """Borra una skill del usuario. Las de fábrica no se pueden borrar."""
        if self.user_skills_dir is None:
            return False
        folder = self.user_skills_dir / skill_id
        if not folder.exists():
            return False
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        self.reload()
        return True
