"""Tests del framework A/B testing y del exportador Prometheus."""
import sys, tempfile
sys.path.insert(0, "backend")
from app.mlops.ab_testing import ABTesting
from app.observability.prometheus import render_metrics


def _ab():
    return ABTesting(tempfile.mktemp(suffix=".json"))


def test_create_and_list_experiment():
    ab = _ab()
    ab.create("modelos", [
        {"name": "A", "model": "mistral:7b", "weight": 50},
        {"name": "B", "model": "qwen2.5:7b", "weight": 50},
    ])
    exps = ab.list()
    assert len(exps) == 1
    assert exps[0]["id"] == "modelos"


def test_assignment_is_deterministic():
    ab = _ab()
    exp = ab.create("x", [
        {"name": "A", "model": "m-a", "weight": 50},
        {"name": "B", "model": "m-b", "weight": 50},
    ])
    # La misma clave da siempre la misma variante.
    v1, _ = ab.assign(exp, "conv-123")
    v2, _ = ab.assign(exp, "conv-123")
    assert v1 == v2


def test_assignment_respects_weights():
    ab = _ab()
    exp = ab.create("x", [
        {"name": "A", "model": "m-a", "weight": 90},
        {"name": "B", "model": "m-b", "weight": 10},
    ])
    counts = {"A": 0, "B": 0}
    for i in range(2000):
        v, _ = ab.assign(exp, f"key-{i}")
        counts[v] += 1
    # A debería llevarse ~90% (margen amplio para no ser flaky).
    assert counts["A"] > counts["B"] * 3


def test_results_leader_but_not_confident_with_small_sample():
    ab = _ab()
    ab.create("x", [
        {"name": "A", "model": "m-a", "weight": 50},
        {"name": "B", "model": "m-b", "weight": 50},
    ])
    # Muestra pequeña (10 c/u): hay líder pero NO ganador con confianza.
    for _ in range(10):
        ab.record("x", "A", True, 100)
    for i in range(10):
        ab.record("x", "B", i < 5, 100)
    res = ab.results("x")
    assert res["leader"] == "A"
    assert res["enough_sample"] is False
    assert res["confident"] is False
    assert res["winner"] is None   # no se declara sin muestra suficiente


def test_results_confident_winner_with_enough_sample():
    ab = _ab()
    ab.create("x", [
        {"name": "A", "model": "m-a", "weight": 50},
        {"name": "B", "model": "m-b", "weight": 50},
    ])
    # Muestra amplia y diferencia clara: A 95% vs B 40% → ganador con confianza.
    for i in range(100):
        ab.record("x", "A", i < 95, 100)
    for i in range(100):
        ab.record("x", "B", i < 40, 100)
    res = ab.results("x")
    assert res["enough_sample"] is True
    assert res["confident"] is True
    assert res["winner"] == "A"
    assert res["test"]["significant"] is True
    assert res["test"]["p_value"] < 0.05


def test_set_active_and_delete():
    ab = _ab()
    ab.create("x", [{"name": "A", "model": "a", "weight": 1},
                    {"name": "B", "model": "b", "weight": 1}])
    assert ab.set_active("x", False) is True
    assert ab.active_experiment() is None
    assert ab.delete("x") is True
    assert ab.get("x") is None


def test_prometheus_render_format():
    summary = {"total_requests": 5, "success_rate_pct": 80.0,
               "p50_latency_ms": 120, "p95_latency_ms": 300, "p99_latency_ms": 500,
               "degradation_rate": 0.0}
    tools = {"by_tool": {"file_write": {"calls": 3, "error_rate": 0.0}}}
    out = render_metrics(summary, tools)
    assert "andromeda_requests_total 5" in out
    assert "andromeda_success_rate 80.0" in out
    assert 'quantile="0.95"' in out
    assert 'andromeda_tool_calls_total{tool="file_write"} 3' in out
    # Formato Prometheus: cada métrica con HELP y TYPE.
    assert "# TYPE andromeda_requests_total counter" in out


# ── Significancia estadística (test z de dos proporciones) ──────────────────
def test_ztest_detects_significant_difference():
    from app.mlops.stats import two_proportion_z_test
    # 95/100 vs 40/100 → diferencia enorme, claramente significativa.
    r = two_proportion_z_test(95, 100, 40, 100)
    assert r["significant"] is True
    assert r["p_value"] < 0.05


def test_ztest_no_significance_when_equal():
    from app.mlops.stats import two_proportion_z_test
    # 50/100 vs 50/100 → sin diferencia.
    r = two_proportion_z_test(50, 100, 50, 100)
    assert r["significant"] is False
    assert r["p_value"] > 0.05


def test_ztest_handles_zero_samples():
    from app.mlops.stats import two_proportion_z_test
    r = two_proportion_z_test(0, 0, 0, 0)
    assert r["significant"] is False
