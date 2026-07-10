"""
lab.py — Laboratorio de IA: fine-tuning ligero, parámetros y entrenamiento con ejemplos.

El fine-tuning pesado (LoRA/QLoRA con GPU) requiere herramientas externas. Lo que
SÍ podemos hacer de forma local y real con Ollama es:
  1. Crear variantes con parámetros personalizados (temperatura, top_p, top_k, etc.)
  2. Hornear un system prompt especializado
  3. Entrenar "few-shot" con pares de ejemplos (MESSAGE user/assistant en el Modelfile)
  4. Importar datasets (JSONL con {prompt, response}) como ejemplos
Esto es fine-tuning ligero genuino: el modelo resultante responde según los ejemplos.
"""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/lab", tags=["lab"])

# Estado de los trabajos de entrenamiento en curso (en memoria)
_jobs: dict[str, dict] = {}


def _slug(text: str, maxlen: int = 24) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:maxlen]


@router.get("/jobs")
async def list_jobs() -> JSONResponse:
    """Lista los trabajos de fine-tuning y su estado."""
    return JSONResponse(content={"jobs": list(_jobs.values())})


@router.post("/finetune")
async def finetune(request: Request) -> JSONResponse:
    """
    Crea una variante fine-tuned de un modelo.
    Body: {
        "base_model": "qwen2.5-coder:7b",
        "variant_name": "mi-experto-python",   (opcional, se genera si falta)
        "system": "Eres un experto en Python...",  (opcional)
        "parameters": {"temperature": 0.5, "top_p": 0.9, "top_k": 40,
                       "repeat_penalty": 1.1, "num_ctx": 4096},  (opcional)
        "examples": [{"user": "...", "assistant": "..."}],  (opcional, few-shot)
    }
    """
    import httpx

    body = await request.json()
    base_model = body.get("base_model", "").strip()
    if not base_model:
        return JSONResponse(content={"error": "base_model requerido"}, status_code=400)

    system = body.get("system", "").strip()
    params = body.get("parameters", {}) or {}
    examples = body.get("examples", []) or []

    # Nombre de la variante
    raw_name = body.get("variant_name", "").strip()
    if raw_name:
        variant = f"{base_model.split(':')[0]}-lab-{_slug(raw_name)}"
    else:
        variant = f"{base_model.split(':')[0]}-lab-{_slug(system or 'custom')}"

    # ── Construir el Modelfile ──────────────────────────────────────────────
    lines = [f"FROM {base_model}"]

    if system:
        system_clean = system.replace('"', "'").strip()
        lines.append(f'SYSTEM """{system_clean}"""')

    # Parámetros (con valores por defecto sensatos y validación de rango)
    safe_params = {
        # básicos
        "temperature":    (params.get("temperature"), 0.0, 2.0, float),
        "top_p":          (params.get("top_p"), 0.0, 1.0, float),
        "top_k":          (params.get("top_k"), 1, 100, int),
        "repeat_penalty": (params.get("repeat_penalty"), 0.5, 2.0, float),
        "num_ctx":        (params.get("num_ctx"), 512, 131072, int),
        # avanzados
        "num_predict":    (params.get("num_predict"), 64, 32768, int),
        "min_p":          (params.get("min_p"), 0.0, 1.0, float),
        "repeat_last_n":  (params.get("repeat_last_n"), 0, 4096, int),
        "seed":           (params.get("seed"), 0, 2**31 - 1, int),
    }
    for pname, (pval, pmin, pmax, cast) in safe_params.items():
        if pval is not None and pval != "":
            try:
                v = cast(float(pval))
                v = max(pmin, min(pmax, v))
                lines.append(f"PARAMETER {pname} {v}")
            except (ValueError, TypeError):
                pass

    # Secuencias de parada (hasta 4)
    for stop in (body.get("stop") or [])[:4]:
        s = str(stop).strip().replace('"', "'")
        if s:
            lines.append(f'PARAMETER stop "{s}"')

    # Ejemplos few-shot → MESSAGE pairs (esto es el "entrenamiento" ligero)
    n_examples = 0
    for ex in examples:
        u = (ex.get("user") or "").strip()
        a = (ex.get("assistant") or "").strip()
        if u and a:
            u_clean = u.replace('"', "'").replace("\n", " ")
            a_clean = a.replace('"', "'").replace("\n", " ")
            lines.append(f'MESSAGE user """{u_clean}"""')
            lines.append(f'MESSAGE assistant """{a_clean}"""')
            n_examples += 1

    modelfile = "\n".join(lines)

    # ── Resolver Ollama y lanzar la creación en background ──────────────────
    try:
        from ..ollama_resolver import resolve_ollama_url
        base_url = await resolve_ollama_url()
    except Exception:
        base_url = request.app.state.settings.ollama_base_url

    if not base_url:
        return JSONResponse(content={"error": "Ollama no disponible"}, status_code=503)

    job_id = variant
    _jobs[job_id] = {
        "id": job_id, "variant": variant, "base_model": base_model,
        "status": "running", "progress": "Iniciando...",
        "n_examples": n_examples, "n_params": len([1 for _, t in safe_params.items() if t[0] is not None]),
    }

    async def do_train():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=15.0), trust_env=False) as client:
                async with client.stream("POST", f"{base_url}/api/create",
                                          json={"name": variant, "modelfile": modelfile}) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            if status:
                                _jobs[job_id]["progress"] = status
                        except json.JSONDecodeError:
                            pass
            _jobs[job_id]["status"] = "finished"
            _jobs[job_id]["progress"] = "Completado"
        except Exception as exc:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["progress"] = f"Error: {str(exc)[:120]}"

    asyncio.create_task(do_train())

    return JSONResponse(content={
        "job_id": job_id,
        "variant": variant,
        "n_examples": n_examples,
        "modelfile_preview": modelfile[:500],
        "message": f"Entrenando «{variant}» con {n_examples} ejemplos. Mira el progreso en la lista de trabajos.",
    })


@router.post("/parse-dataset")
async def parse_dataset(request: Request) -> JSONResponse:
    """
    Convierte un dataset pegado (JSONL o texto) en ejemplos {user, assistant}.
    Body: {"raw": "...", "format": "jsonl|qa"}
    - jsonl: cada línea es {"prompt": "...", "response": "..."} o {"user":..,"assistant":..}
    - qa: pares de líneas P: ... / R: ...
    """
    body = await request.json()
    raw = body.get("raw", "").strip()
    fmt = body.get("format", "jsonl")
    examples = []

    if not raw:
        return JSONResponse(content={"examples": [], "error": "Sin datos"})

    if fmt == "jsonl":
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                u = obj.get("user") or obj.get("prompt") or obj.get("input") or obj.get("instruction") or ""
                a = obj.get("assistant") or obj.get("response") or obj.get("output") or obj.get("completion") or ""
                if u and a:
                    examples.append({"user": str(u), "assistant": str(a)})
            except json.JSONDecodeError:
                continue
    else:  # qa
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        i = 0
        while i < len(lines) - 1:
            l1, l2 = lines[i], lines[i+1]
            if l1[:2].upper() in ("P:", "Q:") and l2[:2].upper() in ("R:", "A:"):
                examples.append({"user": l1[2:].strip(), "assistant": l2[2:].strip()})
                i += 2
            else:
                i += 1

    return JSONResponse(content={
        "examples": examples,
        "count": len(examples),
        "message": f"{len(examples)} ejemplos detectados.",
    })


@router.delete("/variant/{variant_name}")
async def delete_variant(variant_name: str, request: Request) -> JSONResponse:
    """Elimina una variante creada en el Lab."""
    import httpx
    try:
        from ..ollama_resolver import resolve_ollama_url
        base_url = await resolve_ollama_url()
    except Exception:
        base_url = request.app.state.settings.ollama_base_url

    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            r = await client.request("DELETE", f"{base_url}/api/delete",
                                     json={"name": variant_name})
        _jobs.pop(variant_name, None)
        return JSONResponse(content={"deleted": variant_name, "ok": r.status_code < 400})
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.get("/specialists")
async def lab_specialists(request: Request) -> JSONResponse:
    """Lista de especialistas (id, nombre, modelo actual y override) para el selector del Lab."""
    registry = getattr(request.app.state, "registry", None)
    hardware = getattr(request.app.state, "hardware", None)
    if registry is None:
        return JSONResponse(content={"specialists": []})
    overrides = registry.get_all_overrides()
    out = []
    for sp in registry.get_all():
        model, level = registry.resolve_model_for_tier(
            sp.id, hardware.max_tier if hardware else 1,
            (hardware.total_vram_gb * 0.8) if hardware else 999,
        )
        out.append({
            "id": sp.id, "name": sp.name,
            "current_model": model, "level": level,
            "override": overrides.get(sp.id),
        })
    return JSONResponse(content={"specialists": out})


@router.post("/assign")
async def assign_variant(request: Request) -> JSONResponse:
    """
    Asigna una variante del Lab a un especialista (pasa a usarse en el chat).
    Body: {"variant": "qwen3-lab-experto", "specialist_id": "software-engineering"}
    Con variant=null se quita la asignación y vuelve la selección automática.
    """
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        return JSONResponse(content={"error": "Registry no disponible"}, status_code=503)
    body = await request.json()
    specialist_id = body.get("specialist_id", "").strip()
    variant = body.get("variant")
    if not specialist_id:
        return JSONResponse(content={"error": "specialist_id requerido"}, status_code=400)
    try:
        registry.get_by_id(specialist_id)
    except ValueError:
        return JSONResponse(content={"error": f"Especialista '{specialist_id}' no existe"},
                            status_code=404)

    # Validar que la variante existe en Ollama AHORA y refrescar la lista del registry
    if variant:
        import httpx
        try:
            from ..ollama_resolver import resolve_ollama_url
            base_url = await resolve_ollama_url()
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                r = await client.get(f"{base_url}/api/tags")
                live = [m.get("name", "") for m in r.json().get("models", [])]
            registry.set_available_models(live)
            if variant not in live:
                return JSONResponse(
                    content={"error": f"«{variant}» no existe en Ollama. ¿Terminó el entrenamiento?"},
                    status_code=404)
        except Exception:
            pass  # Ollama offline: permitir la asignación igualmente (se usará al volver)

    registry.set_model_override(specialist_id, variant or None)
    if variant:
        msg = f"«{variant}» asignado a {specialist_id}. Ya se usa en el chat."
    else:
        msg = f"{specialist_id} vuelve a selección automática de modelo."
    return JSONResponse(content={"ok": True, "message": msg,
                                 "overrides": registry.get_all_overrides()})


@router.post("/test")
async def test_variant(request: Request) -> JSONResponse:
    """
    Prueba una variante con un prompt corto (generación única, sin streaming).
    Body: {"variant": "...", "prompt": "..."}
    """
    import httpx
    body = await request.json()
    variant = body.get("variant", "").strip()
    prompt = body.get("prompt", "").strip()
    if not variant or not prompt:
        return JSONResponse(content={"error": "variant y prompt requeridos"}, status_code=400)

    try:
        from ..ollama_resolver import resolve_ollama_url
        base_url = await resolve_ollama_url()
    except Exception:
        base_url = request.app.state.settings.ollama_base_url
    if not base_url:
        return JSONResponse(content={"error": "Ollama no disponible"}, status_code=503)

    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            r = await client.post(f"{base_url}/api/generate",
                                  json={"model": variant, "prompt": prompt[:2000],
                                        "stream": False})
            data = r.json()
        return JSONResponse(content={
            "response": data.get("response", ""),
            "eval_count": data.get("eval_count", 0),
            "total_ms": round(data.get("total_duration", 0) / 1e6),
        })
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)[:200]}, status_code=502)
