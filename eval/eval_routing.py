#!/usr/bin/env python3
"""
eval_routing.py — Banco de pruebas del enrutamiento de Andromeda Orquesta.

Mide si el orquestador toma las decisiones correctas SIN necesitar modelos ni
Ollama: evalúa la capa de POLÍTICA (dominio, tier de potencia, especialista).

Uso:
    python eval/eval_routing.py
    python eval/eval_routing.py --dataset eval/routing_dataset.jsonl --json

Métricas:
  - domain_acc:     % de dominios detectados correctamente
  - specialist_acc: % de especialistas elegidos correctamente
  - tier_ok:        % de tiers dentro del rango esperado (tier_min/tier_max)
  - tier_mae:       error absoluto medio del tier (cuán lejos del rango)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ANDROMEDA_SPECIALISTS_CONFIG_PATH", str(ROOT / "config/specialists.yaml"))

import warnings
warnings.filterwarnings("ignore")


def _build_registry():
    from app.specialists.registry import SpecialistRegistry
    cfg = str(ROOT / "config/specialists.yaml")
    reg = SpecialistRegistry(cfg)
    reg._load_yaml(cfg)
    for sid in ["software-engineering", "technical-writer", "verifier",
                "summarizer", "generalist", "it-ops"]:
        try:
            reg.update_model(sid, "", True)
        except Exception:
            pass
    # Modelos de todos los tamaños disponibles para no limitar por hardware.
    reg.set_available_models([
        "qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b",
        "qwen2.5-coder:72b", "llama3.2:3b", "mistral:7b", "llama3.1:8b",
        "llama3.1:70b", "qwen2.5:14b", "qwen2.5:32b",
    ])
    return reg


def _hardware():
    from app.models.schemas import HardwareInfo
    return HardwareInfo(os="Linux", cpu_model="x", cpu_cores=16, ram_total_gb=64,
                        ram_available_gb=50, gpus=[], total_vram_gb=48,
                        acceleration="gpu", max_tier=4)


class _RP:
    effective_parallel = 4
    eligible_strategies = ["single", "parallel_merge", "best_of_n", "synthesis",
                           "confidence_weighted", "vote"]


class _Req:
    def __init__(self, prompt):
        self.specialists = None
        self.strategy = "auto"
        self.max_parallel = None
        self.prompt = prompt


def evaluate(dataset_path: Path) -> dict:
    from app.core.orchestrator import build_plan, _detect_domain

    reg = _build_registry()
    hw = _hardware()
    active = reg.get_active()

    cases = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    rows = []
    dom_ok = spec_ok = tier_ok = 0
    tier_err_sum = 0

    for case in cases:
        prompt = case["prompt"]
        plan = build_plan(chat_request=_Req(prompt), active_specialists=active,
                          classifier_result=None, runtime_policy=_RP(),
                          registry=reg, hardware=hw)
        got_domain = _detect_domain(prompt)
        got_spec = plan.specialists[0].id if plan.specialists else None
        got_tier = plan.power_tier

        # Dominio
        d_ok = (got_domain == case.get("domain"))
        # Especialista
        s_ok = (got_spec == case.get("specialist"))
        # Tier dentro de rango [tier_min, tier_max]
        tmin = case.get("tier_min", 1)
        tmax = case.get("tier_max", 4)
        t_ok = (tmin <= got_tier <= tmax)
        # Error de tier: distancia al rango
        if got_tier < tmin:
            t_err = tmin - got_tier
        elif got_tier > tmax:
            t_err = got_tier - tmax
        else:
            t_err = 0

        dom_ok += d_ok; spec_ok += s_ok; tier_ok += t_ok; tier_err_sum += t_err
        rows.append({
            "prompt": prompt[:55],
            "domain": f"{got_domain}{'✓' if d_ok else '✗('+str(case.get('domain'))+')'}",
            "spec": f"{got_spec}{'✓' if s_ok else '✗('+str(case.get('specialist'))+')'}",
            "tier": f"T{got_tier}{'✓' if t_ok else '✗['+str(tmin)+'-'+str(tmax)+']'}",
        })

    n = len(cases)
    return {
        "n": n,
        "domain_acc": round(dom_ok / n, 3),
        "specialist_acc": round(spec_ok / n, 3),
        "tier_ok": round(tier_ok / n, 3),
        "tier_mae": round(tier_err_sum / n, 3),
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "eval/routing_dataset.jsonl"))
    ap.add_argument("--json", action="store_true", help="salida JSON")
    args = ap.parse_args()

    res = evaluate(Path(args.dataset))

    if args.json:
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=2))
        return

    print("\n" + "=" * 72)
    print("  BANCO DE PRUEBAS — Enrutamiento de Andromeda Orquesta")
    print("=" * 72)
    for r in res["rows"]:
        print(f"  {r['prompt']:<56}")
        print(f"     dominio={r['domain']:<22} esp={r['spec']:<28} {r['tier']}")
    print("-" * 72)
    print(f"  Casos:                {res['n']}")
    print(f"  Precisión dominio:    {res['domain_acc']*100:.1f}%")
    print(f"  Precisión especialista:{res['specialist_acc']*100:.1f}%")
    print(f"  Tier en rango:        {res['tier_ok']*100:.1f}%")
    print(f"  Error medio de tier:  {res['tier_mae']:.2f}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
