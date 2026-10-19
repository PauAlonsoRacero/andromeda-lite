"""
rag/bm25.py — Recuperación local de documentos (RAG) sin dependencias.

Núcleo del RAG de Andromeda Pro: un índice BM25 (Okapi) implementado en Python
puro, con persistencia JSON en el directorio de datos. No requiere embeddings
ni servicios externos, así que funciona 100% offline desde el primer segundo;
cuando hay Ollama disponible, la capa superior puede re-rankear con embeddings
(mejora opcional, no dependencia).

Diseño:
  - Los documentos se trocean en chunks (~700 chars con solape) al indexar.
  - BM25 clásico (k1=1.5, b=0.75) sobre tokens normalizados (minúsculas, sin
    acentos, \\w+). Suficiente para docs técnicos y notas de proyecto.
  - Escritura atómica del índice para sobrevivir cierres bruscos.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from pathlib import Path

_K1 = 1.5
_B = 0.75
_CHUNK_SIZE = 700
_CHUNK_OVERLAP = 120

# Tope del índice. El índice se carga entero en memoria en cada consulta, así
# que sin límite la app se degrada poco a poco a medida que se indexa más, sin
# que el usuario entienda por qué. Al superarlo se descartan los documentos
# menos usados, no los más antiguos: un manual de referencia consultado a
# diario debe sobrevivir a un borrador que se indexó ayer y nadie ha vuelto a
# mirar.
_MAX_CHUNKS = 5000
_MAX_DOCUMENTS = 500

logger = logging.getLogger("andromeda.rag")

try:
    from app.observability import diagnostics as diag
except Exception:                                        # pragma: no cover
    class _Nulo:                                         # el registro nunca es obligatorio
        @staticmethod
        def log(*a, **k): pass
        @staticmethod
        def is_enabled(): return False
    diag = _Nulo()

_lock = threading.Lock()


def _normalize(text: str) -> list[str]:
    """minúsculas + sin acentos + tokens \\w+ (>=2 chars)."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return [w for w in re.findall(r"\w+", t) if len(w) >= 2]


def chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Trocea por párrafos, agrupando hasta ~size con solape entre chunks."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = f"{buf}\n\n{p}" if buf else p
            continue
        if buf:
            chunks.append(buf)
        # párrafo enorme: cortar duro con solape
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap:]
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


class BM25Index:
    """Índice BM25 incremental y persistente."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        # chunks: [{id, doc_id, text, meta, tokens(len), tf}]
        self.chunks: list[dict] = []
        self.df: Counter = Counter()          # doc-frequency por término
        self._load()

    # ── persistencia ──────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.chunks = data.get("chunks", [])
                self.df = Counter(data.get("df", {}))
        except Exception:
            self.chunks, self.df = [], Counter()

    def _save(self) -> None:
        """Persiste el índice. Un fallo de disco no puede romper el chat.

        Si el disco está lleno o falta permiso, se registra y se continúa: el
        índice sigue vivo en memoria durante la sesión. Perder la persistencia
        es molesto; perder la petición del usuario, mucho peor.
        """
        try:
            tmp = self.path.with_suffix(".tmp")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(
                {"chunks": self.chunks, "df": dict(self.df)},
                ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning(f"No se pudo guardar el índice RAG: {exc}")

    # ── indexado ──────────────────────────────────────────────────────────
    def add_document(self, doc_id: str, text: str, meta: dict | None = None) -> int:
        """Indexa (o re-indexa) un documento troceado. Devuelve nº de chunks."""
        with _lock:
            self._remove_doc_unlocked(doc_id)
            n = 0
            for i, ch in enumerate(chunk_text(text)):
                toks = _normalize(ch)
                if not toks:
                    continue
                tf = Counter(toks)
                for term in tf:
                    self.df[term] += 1
                self.chunks.append({
                    "id": f"{doc_id}#{i}", "doc_id": doc_id, "text": ch,
                    "meta": meta or {}, "len": len(toks), "tf": dict(tf),
                    "hits": 0,                       # veces recuperado
                    "added": time.time(),            # desempate para los no usados
                })
                n += 1
            self._prune_if_needed()
            self._save()
            return n

    def remove_document(self, doc_id: str) -> int:
        with _lock:
            n = self._remove_doc_unlocked(doc_id)
            self._save()
            return n

    def _remove_doc_unlocked(self, doc_id: str) -> int:
        old = [c for c in self.chunks if c["doc_id"] == doc_id]
        for c in old:
            for term in c["tf"]:
                self.df[term] -= 1
                if self.df[term] <= 0:
                    del self.df[term]
        self.chunks = [c for c in self.chunks if c["doc_id"] != doc_id]
        return len(old)

    # ── consulta ──────────────────────────────────────────────────────────

    def _prune_if_needed(self) -> int:
        """Descarta documentos si el índice supera el tope. Devuelve cuántos.

        Se ordena por uso: cuántas veces se ha recuperado cada documento y,
        para desempatar entre los nunca usados, cuál se indexó antes. Descartar
        por antigüedad a secas tiraría documentos de referencia que se
        consultan a diario solo por llevar tiempo indexados.
        """
        docs = {c["doc_id"] for c in self.chunks}
        if len(self.chunks) <= _MAX_CHUNKS and len(docs) <= _MAX_DOCUMENTS:
            return 0

        # Puntuación por documento: usos totales, y el más reciente como desempate
        puntos: dict[str, tuple[int, float]] = {}
        for c in self.chunks:
            usos, cuando = puntos.get(c["doc_id"], (0, 0.0))
            puntos[c["doc_id"]] = (usos + c.get("hits", 0),
                                   max(cuando, c.get("added", 0.0)))
        orden = sorted(puntos, key=lambda d: puntos[d])     # los peores primero

        descartados = 0
        for doc_id in orden:
            if len(self.chunks) <= _MAX_CHUNKS and \
               len({c["doc_id"] for c in self.chunks}) <= _MAX_DOCUMENTS:
                break
            self._remove_doc_unlocked(doc_id)
            descartados += 1
        if descartados:
            logger.info(f"Índice RAG podado: {descartados} documentos menos usados "
                        f"descartados (tope: {_MAX_DOCUMENTS} docs / {_MAX_CHUNKS} fragmentos)")
        return descartados

    def query(self, q: str, k: int = 4) -> list[dict]:
        """Top-k chunks por BM25. [{id, doc_id, text, meta, score}]"""
        q_terms = _normalize(q)
        if not q_terms or not self.chunks:
            return []
        N = len(self.chunks)
        avgdl = sum(c["len"] for c in self.chunks) / N
        scored = []
        for c in self.chunks:
            s = 0.0
            for term in q_terms:
                f = c["tf"].get(term, 0)
                if not f:
                    continue
                idf = math.log(1 + (N - self.df[term] + 0.5) / (self.df[term] + 0.5))
                s += idf * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * c["len"] / avgdl))
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        top = scored[:k]
        # Registrar el uso: es lo que permite podar por relevancia real en vez
        # de por antigüedad. No se persiste en cada consulta (sería un escritura
        # por búsqueda); se guarda con el siguiente cambio del índice.
        for _, c in top:
            c["hits"] = c.get("hits", 0) + 1
        return [{**c, "score": round(sc, 3)} for sc, c in top]

    def stats(self) -> dict:
        return {"chunks": len(self.chunks),
                "documents": len({c["doc_id"] for c in self.chunks}),
                "terms": len(self.df)}
