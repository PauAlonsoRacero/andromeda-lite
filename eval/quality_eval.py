#!/usr/bin/env python3
"""
quality_eval.py — Evaluación de calidad offline (golden set + LLM-as-judge).

Cierra el círculo del A/B: el A/B mide satisfacción en producción, pero antes de
desplegar un modelo conviene evaluarlo en frío contra un conjunto dorado. Este
harness:

  1. Envía cada prompt del golden set al modelo a evaluar (vía Ollama).
  2. Pide a un modelo JUEZ que puntúe la respuesta de 1 a 5 según un criterio.
  3. Agrega resultados por categoría y un score global.

Es el patrón "LLM-as-judge", estándar para evaluar LLMs sin etiquetar a mano.
Sin dependencias externas (urllib stdlib). Ejecutable en CI o a demanda.

Uso:
    python eval/quality_eval.py --model mistral:7b --judge llama3:8b
    python eval/quality_eval.py --model mistral:7b --judge llama3:8b --json out.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
GOLDEN = Path(__file__).parent / "golden_set.jsonl"

_JUDGE_PROMPT = """Eres un evaluador estricto de respuestas de IA. Puntúa la RESPUESTA del 1 al 5
según si cumple el CRITERIO (5 = perfecta, 1 = muy mala).

PREGUNTA: {prompt}
CRITERIO: {criteria}
RESPUESTA: {answer}

Devuelve SOLO un JSON: {{"score": <1-5>, "reason": "<motivo en una frase>"}}"""


def _ollama_generate(model: str, prompt: str, timeout: float = 120) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.0},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("message", {}).get("content", "")


def _parse_score(text: str) -> tuple[int, str]:
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            score = int(obj.get("score", 0))
            return max(1, min(5, score)), str(obj.get("reason", ""))[:160]
        except Exception:
            pass
    # Fallback: buscar un número 1-5 suelto.
    m = re.search(r'\b([1-5])\b', text)
    return (int(m.group(1)) if m else 0), "sin formato JSON"


def run(model: str, judge: str) -> dict:
    cases = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    results, by_cat = [], {}
    for c in cases:
        t0 = time.time()
        try:
            answer = _ollama_generate(model, c["prompt"])
        except Exception as e:
            answer = f"[ERROR: {e}]"
        latency = (time.time() - t0) * 1000

        judge_raw = ""
        try:
            judge_raw = _ollama_generate(judge, _JUDGE_PROMPT.format(
                prompt=c["prompt"], criteria=c["criteria"], answer=answer))
        except Exception as e:
            judge_raw = f'{{"score": 0, "reason": "juez falló: {e}"}}'
        score, reason = _parse_score(judge_raw)

        results.append({"id": c["id"], "category": c["category"], "score": score,
                        "latency_ms": round(latency), "reason": reason})
        by_cat.setdefault(c["category"], []).append(score)
        print(f"  [{c['id']:<10}] {c['category']:<14} score={score}/5  ({round(latency)}ms)  {reason}")

    valid = [r["score"] for r in results if r["score"] > 0]
    overall = sum(valid) / len(valid) if valid else 0
    cat_avg = {cat: round(sum(s) / len(s), 2) for cat, s in by_cat.items()}
    return {
        "model": model, "judge": judge,
        "overall_score": round(overall, 2),
        "by_category": cat_avg,
        "n_cases": len(results),
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Modelo a evaluar (Ollama)")
    ap.add_argument("--judge", required=True, help="Modelo juez (Ollama)")
    ap.add_argument("--json", help="Guardar el informe en este archivo JSON")
    ap.add_argument("--register", action="store_true",
                    help="Registrar el modelo en el Model Registry con su score")
    ap.add_argument("--api", default="http://127.0.0.1:8000",
                    help="URL del backend para --register")
    args = ap.parse_args()

    print(f"\nEvaluando '{args.model}' · juez '{args.judge}' · {GOLDEN.name}\n")
    report = run(args.model, args.judge)

    print(f"\n── Resultado ──")
    print(f"Score global: {report['overall_score']}/5  ({report['n_cases']} casos)")
    for cat, avg in sorted(report["by_category"].items()):
        print(f"  {cat:<16} {avg}/5")

    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme guardado en {args.json}")

    if args.register:
        # Registrar el modelo evaluado con su score en el Model Registry.
        # Cierra el ciclo: evaluar offline → registrar versión con su nota.
        try:
            body = json.dumps({
                "model": args.model,
                "eval_score": report["overall_score"],
                "notes": f"golden_set eval · juez {args.judge} · {report['n_cases']} casos",
            }).encode("utf-8")
            req = urllib.request.Request(f"{args.api}/api/registry", data=body,
                                         headers={"Content-Type": "application/json"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=10) as resp:
                entry = json.loads(resp.read().decode("utf-8"))
            print(f"\nRegistrado en el Model Registry como {entry.get('version')} "
                  f"(id {entry.get('id')}, estado {entry.get('stage')}).")
        except Exception as e:
            print(f"\nNo se pudo registrar en el Model Registry: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
