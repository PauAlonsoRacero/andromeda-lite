#!/usr/bin/env python3
"""
mlflow_compare.py — Compara modelos a partir de los runs registrados en MLflow.

Consulta el servidor MLflow, agrupa los runs por modelo y muestra una tabla con
latencia media, ttft medio y tasa de éxito de cada uno. Es la cara "analítica"
del versionado: ver qué modelo rinde mejor a lo largo del tiempo, con datos.

Uso:
    python scripts/mlflow_compare.py --uri http://localhost:5001
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="http://localhost:5001", help="URI del servidor MLflow")
    ap.add_argument("--experiment", default="andromeda")
    args = ap.parse_args()

    try:
        import mlflow
    except ImportError:
        print("Falta el paquete 'mlflow'. Instala con: pip install mlflow", file=sys.stderr)
        return 1

    mlflow.set_tracking_uri(args.uri)
    client = mlflow.tracking.MlflowClient()

    exp = client.get_experiment_by_name(args.experiment)
    if not exp:
        print(f"No existe el experimento '{args.experiment}' en {args.uri}", file=sys.stderr)
        return 1

    runs = client.search_runs([exp.experiment_id], max_results=5000)
    if not runs:
        print("No hay runs registrados todavía.")
        return 0

    # Agrupar por modelo (param 'model').
    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "lat": 0.0, "ttft": 0.0, "ok": 0})
    for r in runs:
        model = r.data.params.get("model", "desconocido")
        m = r.data.metrics
        a = agg[model]
        a["n"] += 1
        a["lat"] += m.get("latency_ms", 0.0)
        a["ttft"] += m.get("ttft_ms", 0.0)
        a["ok"] += 1 if m.get("success", 0.0) >= 1.0 else 0

    print(f"\nComparación de modelos · experimento '{args.experiment}' · {len(runs)} runs\n")
    print(f"{'Modelo':<28}{'Runs':>6}{'Lat media (ms)':>16}{'TTFT (ms)':>12}{'Éxito':>9}")
    print("-" * 71)
    for model, a in sorted(agg.items(), key=lambda kv: kv[1]["lat"] / max(kv[1]["n"], 1)):
        n = a["n"]
        print(f"{model:<28}{n:>6}{a['lat']/n:>16.0f}{a['ttft']/n:>12.0f}{a['ok']/n*100:>8.0f}%")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
