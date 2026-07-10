"""
context.py — Pipeline de contexto de proyecto.

Permite a Andromeda entender un proyecto de código completo:
  1. El usuario carga su proyecto (ruta local o ZIP)
  2. Andromeda indexa los archivos relevantes
  3. Las IAs responden con contexto completo del proyecto
  4. Útil para: code review, refactoring, generación de docs

Endpoints:
  POST /api/context/index      → indexar un directorio
  GET  /api/context/summary    → resumen del proyecto indexado
  POST /api/context/query      → preguntar con contexto del proyecto
  DELETE /api/context          → limpiar el índice
"""

import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("andromeda.context")
router = APIRouter()

# Extensiones de código soportadas
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java',
    '.cpp', '.c', '.h', '.cs', '.rb', '.php', '.swift', '.kt',
    '.yaml', '.yml', '.json', '.toml', '.env.example',
    '.md', '.sql', '.sh', '.ps1', '.dockerfile',
}

MAX_FILE_SIZE    = 50_000   # 50KB por archivo
MAX_TOTAL_TOKENS = 80_000   # ~80K tokens de contexto total
MAX_FILES        = 100


def _should_index(path: Path) -> bool:
    """Decide si un archivo debe indexarse."""
    if path.name.startswith('.'): return False
    if any(x in path.parts for x in ['node_modules', '__pycache__', '.git',
                                       'dist', 'build', '.venv', 'venv']): return False
    return path.suffix.lower() in CODE_EXTENSIONS or path.name in [
        'Dockerfile', 'Makefile', 'Procfile', '.env.example'
    ]


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


@router.post("/index")
async def index_project(request: Request) -> JSONResponse:
    """
    Indexa un directorio de proyecto para dar contexto a las IAs.
    El índice se guarda en memoria del proceso (por sesión).
    """
    body = await request.json()
    path = body.get("path", "")

    if not path:
        return JSONResponse(status_code=400, content={"error": "path requerido"})

    project_path = Path(path)
    if not project_path.exists():
        return JSONResponse(status_code=404, content={
            "error": f"Directorio no encontrado: {path}"
        })

    files_indexed = []
    total_tokens  = 0
    skipped       = []

    for file_path in sorted(project_path.rglob("*")):
        if not file_path.is_file(): continue
        if not _should_index(file_path): continue
        if len(files_indexed) >= MAX_FILES:
            skipped.append(str(file_path.relative_to(project_path)))
            continue

        try:
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                skipped.append(f"{file_path.relative_to(project_path)} (demasiado grande)")
                continue

            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tokens  = _estimate_tokens(content)

            if total_tokens + tokens > MAX_TOTAL_TOKENS:
                skipped.append(f"{file_path.relative_to(project_path)} (límite tokens)")
                continue

            rel_path = str(file_path.relative_to(project_path))
            files_indexed.append({
                "path":    rel_path,
                "content": content,
                "tokens":  tokens,
                "ext":     file_path.suffix,
            })
            total_tokens += tokens
        except Exception as exc:
            skipped.append(f"{file_path.name}: {exc}")

    # Guardar en app.state
    request.app.state.project_context = {
        "path":          str(project_path),
        "name":          project_path.name,
        "files":         files_indexed,
        "total_tokens":  total_tokens,
        "total_files":   len(files_indexed),
        "skipped":       skipped,
    }

    logger.info(f"Proyecto indexado: {project_path.name} — {len(files_indexed)} archivos, ~{total_tokens} tokens")

    return JSONResponse(content={
        "success":      True,
        "project":      project_path.name,
        "files_indexed":len(files_indexed),
        "total_tokens": total_tokens,
        "skipped_count":len(skipped),
        "skipped":      skipped[:10],
    })


@router.get("/summary")
async def get_context_summary(request: Request) -> JSONResponse:
    """Resumen del proyecto actualmente indexado."""
    ctx = getattr(request.app.state, 'project_context', None)
    if not ctx:
        return JSONResponse(content={"indexed": False})

    # Agrupar archivos por extensión
    by_ext = {}
    for f in ctx["files"]:
        ext = f["ext"] or "other"
        by_ext[ext] = by_ext.get(ext, 0) + 1

    return JSONResponse(content={
        "indexed":       True,
        "project":       ctx["name"],
        "path":          ctx["path"],
        "total_files":   ctx["total_files"],
        "total_tokens":  ctx["total_tokens"],
        "by_extension":  by_ext,
        "file_list":     [f["path"] for f in ctx["files"]],
    })


@router.post("/query")
async def query_with_context(request: Request) -> JSONResponse:
    """
    Responde una pregunta con contexto completo del proyecto indexado.
    Construye un prompt con todos los archivos relevantes.
    """
    import httpx
    body     = await request.json()
    question = body.get("question", "")
    files    = body.get("files")   # None = todos
    model    = body.get("model")

    ctx      = getattr(request.app.state, 'project_context', None)
    settings = request.app.state.settings
    registry = request.app.state.registry

    if not ctx:
        return JSONResponse(status_code=400, content={
            "error": "Ningún proyecto indexado. Usa POST /api/context/index primero."
        })

    if not question:
        return JSONResponse(status_code=400, content={"error": "question requerida"})

    # Seleccionar archivos
    selected = ctx["files"]
    if files:
        selected = [f for f in selected if f["path"] in files]

    # Construir contexto del proyecto
    project_context = f"# Proyecto: {ctx['name']}\n\n"
    for f in selected:
        project_context += f"## Archivo: {f['path']}\n```{f['ext'].lstrip('.')}\n{f['content']}\n```\n\n"

    full_prompt = f"{project_context}\n---\n\n{question}"

    # Usar el mejor modelo disponible
    if not model:
        active = registry.get_active()
        sw_eng = next((s for s in active if s.id == 'software-engineering'), None)
        model  = (sw_eng or active[0] if active else None)
        model  = model.model_name if model else "mistral:7b"

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model":    model,
                    "messages": [
                        {"role": "system", "content":
                            "Eres un experto en análisis de código. Tienes acceso al código fuente "
                            "completo del proyecto. Responde con precisión técnica basándote en el código real."},
                        {"role": "user", "content": full_prompt},
                    ],
                    "options": {"temperature": 0.3, "num_predict": 2048},
                    "stream":  False,
                },
                timeout=120.0,
            )
            r.raise_for_status()
            response = r.json().get("message", {}).get("content", "")

        return JSONResponse(content={
            "response":      response,
            "model":         model,
            "files_used":    len(selected),
            "tokens_sent":   _estimate_tokens(full_prompt),
            "project":       ctx["name"],
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.delete("")
async def clear_context(request: Request) -> JSONResponse:
    """Elimina el contexto del proyecto de la memoria."""
    if hasattr(request.app.state, 'project_context'):
        del request.app.state.project_context
    return JSONResponse(content={"success": True, "message": "Contexto eliminado"})
