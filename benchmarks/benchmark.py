#!/usr/bin/env python3
"""
benchmark.py — Banco de pruebas de rendimiento de Andromeda.

Mide, sobre TU hardware y TUS modelos descargados, el rendimiento real del
pipeline de orquestación: latencia, time-to-first-token (TTFT), tokens/s, y
cómo escala con 1 → 2 → 3 → 4 IAs en paralelo.

Genera:
  - benchmarks/results.json   (datos crudos, para gráficas)
  - benchmarks/REPORT.md      (informe legible con tablas)

Uso:
    # Con Andromeda corriendo (docker o app):
    python benchmarks/benchmark.py --url http://localhost:8000

    # Prompts personalizados:
    python benchmarks/benchmark.py --prompts mis_prompts.txt

Requisitos: Ollama corriendo con al menos un modelo descargado.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).parent

# Prompts representativos de distintos tipos de tarea (cubren los modos del
# orquestador: fast / balanced / deep).
DEFAULT_PROMPTS = [
    ("simple",   "Hola, ¿qué tal?"),
    ("factual",  "¿Cuál es la capital de Francia y cuántos habitantes tiene?"),
    ("código",   "Escribe una función en Python que calcule la sucesión de Fibonacci."),
    ("análisis", "Explica las ventajas y desventajas de los microservicios frente a un monolito."),
    ("creativo", "Redacta un breve ensayo sobre el impacto de la IA local en la privacidad."),
]


def _post_chat(client: httpx.Client, url: str, prompt: str,
               max_parallel: int | None) -> dict:
    """Lanza una petición de chat en streaming y mide tiempos."""
    body = {"prompt": prompt, "stream": True, "strategy": "auto"}
    if max_parallel:
        body["max_parallel"] = max_parallel
        body["parallel_policy"] = "max_hardware"

    t_start = time.perf_counter()
    ttft = None
    tokens = 0
    content_chars = 0
    meta = {}

    with client.stream("POST", f"{url}/api/chat", json=body, timeout=300) as r:
        for line in r.iter_lines():
            if not line.startswith("data: ") or "[DONE]" in line:
                continue
            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            c = chunk.get("content", "")
            if c and ttft is None:
                ttft = (time.perf_counter() - t_start) * 1000
            if c:
                tokens += 1
                content_chars += len(c)
            if chunk.get("is_final"):
                meta = chunk.get("metadata", {})

    total_ms = (time.perf_counter() - t_start) * 1000
    tok_per_s = (tokens / (total_ms / 1000)) if total_ms > 0 else 0
    return {
        "total_ms": round(total_ms, 1),
        "ttft_ms": round(ttft or 0, 1),
        "tokens": tokens,
        "chars": content_chars,
        "tokens_per_s": round(tok_per_s, 1),
        "specialists_used": meta.get("specialists_used", []),
        "strategy": meta.get("strategy_used"),
        "output_ai_used": meta.get("output_ai_used", False),
        "error": bool(meta.get("error")),
    }


def detect_hardware(client: httpx.Client, url: str) -> dict:
    try:
        r = client.get(f"{url}/api/health/hardware", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def run_benchmark(url: str, prompts, runs: int, parallel_levels) -> dict:
    results = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "host_os": platform.platform(),
            "python": platform.python_version(),
        },
        "runs": [],
    }
    with httpx.Client() as client:
        hw = detect_hardware(client, url)
        results["meta"]["hardware"] = hw
        print(f"Hardware: tier T{hw.get('max_tier','?')}, "
              f"VRAM {hw.get('total_vram_gb','?')}GB\n")

        for n in parallel_levels:
            for label, prompt in prompts:
                samples = []
                for i in range(runs):
                    print(f"  [{n} IA] {label:10} run {i+1}/{runs}...", end="", flush=True)
                    res = _post_chat(client, url, prompt, n if n > 1 else 1)
                    samples.append(res)
                    print(f" {res['total_ms']:.0f}ms TTFT={res['ttft_ms']:.0f}ms "
                          f"{res['tokens_per_s']:.0f}tok/s "
                          f"({'×' if res['error'] else '✓'})")
                ok = [s for s in samples if not s["error"]]
                if ok:
                    results["runs"].append({
                        "n_parallel": n,
                        "task": label,
                        "prompt": prompt,
                        "median_total_ms": round(statistics.median(s["total_ms"] for s in ok), 1),
                        "median_ttft_ms": round(statistics.median(s["ttft_ms"] for s in ok), 1),
                        "median_tokens_per_s": round(statistics.median(s["tokens_per_s"] for s in ok), 1),
                        "strategy": ok[-1]["strategy"],
                        "output_ai_used": ok[-1]["output_ai_used"],
                        "specialists": ok[-1]["specialists_used"],
                        "samples": len(ok),
                    })
    return results


def write_report(results: dict) -> None:
    (HERE / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))

    hw = results["meta"].get("hardware", {})
    lines = [
        "# Andromeda — Informe de Rendimiento",
        "",
        f"**Fecha:** {results['meta']['timestamp']}  ",
        f"**Sistema:** {results['meta']['host_os']}  ",
        f"**Hardware:** tier T{hw.get('max_tier','?')}, "
        f"{hw.get('total_vram_gb','?')}GB VRAM, "
        f"GPU: {hw.get('gpu_name', hw.get('acceleration','?'))}  ",
        "",
        "## Resultados por nº de IAs y tipo de tarea",
        "",
        "| IAs | Tarea | Latencia (md) | TTFT (md) | tok/s (md) | Estrategia | IA-salida |",
        "|----:|-------|--------------:|----------:|-----------:|------------|:---------:|",
    ]
    for r in results["runs"]:
        lines.append(
            f"| {r['n_parallel']} | {r['task']} | {r['median_total_ms']:.0f} ms | "
            f"{r['median_ttft_ms']:.0f} ms | {r['median_tokens_per_s']:.0f} | "
            f"{r['strategy'] or '—'} | {'✓' if r['output_ai_used'] else '—'} |"
        )
    lines += [
        "",
        "## Cómo leer esto",
        "",
        "- **Latencia (md):** mediana del tiempo total hasta la respuesta completa.",
        "- **TTFT:** time-to-first-token — cuánto tardas en ver el primer texto.",
        "- **tok/s:** velocidad de generación.",
        "- **IA-salida:** si se aplicó la etapa de pulido final (solo con 2+ IAs).",
        "",
        "Métricas tomadas como mediana de varias ejecuciones para reducir ruido.",
    ]
    (HERE / "REPORT.md").write_text("\n".join(lines))
    print(f"\n✓ Informe: {HERE / 'REPORT.md'}")
    print(f"✓ Datos:   {HERE / 'results.json'}")


def main():
    ap = argparse.ArgumentParser(description="Benchmark de Andromeda")
    ap.add_argument("--url", default="http://localhost:8000", help="URL del backend")
    ap.add_argument("--runs", type=int, default=3, help="Repeticiones por caso")
    ap.add_argument("--parallel", default="1,2,3", help="Niveles de paralelismo (coma)")
    ap.add_argument("--prompts", help="Fichero de prompts (uno por línea)")
    args = ap.parse_args()

    prompts = DEFAULT_PROMPTS
    if args.prompts:
        custom = [l.strip() for l in Path(args.prompts).read_text().splitlines() if l.strip()]
        prompts = [(f"custom{i+1}", p) for i, p in enumerate(custom)]

    levels = [int(x) for x in args.parallel.split(",")]
    print(f"Benchmark Andromeda → {args.url}")
    print(f"Niveles paralelos: {levels} | {args.runs} runs por caso\n")

    results = run_benchmark(args.url, prompts, args.runs, levels)
    write_report(results)


if __name__ == "__main__":
    main()
