"""Tests del histórico de calidad: snapshot, drift y SLO."""
import sys, tempfile, time
sys.path.insert(0, "backend")
from app.mlops.quality_history import QualityHistory


def _m(total=10, sr=99.0, p95=2000, p50=800, deg=0.0):
    return {"total_requests": total, "success_rate_pct": sr, "p95_latency_ms": p95,
            "p50_latency_ms": p50, "degradation_rate_pct": deg}


def test_snapshot_throttles_by_bucket():
    qh = QualityHistory(tempfile.mktemp(suffix=".json"))
    assert qh.snapshot(_m(), 80.0) is True
    # Segundo snapshot inmediato: mismo cubo de tiempo → no guarda.
    assert qh.snapshot(_m(), 80.0) is False
    assert len(qh.series()) == 1


def test_snapshot_ignores_zero_requests():
    qh = QualityHistory(tempfile.mktemp(suffix=".json"))
    assert qh.snapshot(_m(total=0), None) is False
    assert qh.series() == []


def test_slo_breach_detected():
    qh = QualityHistory(tempfile.mktemp(suffix=".json"),
                        slo={"success_rate_min": 95, "p95_latency_max": 5000, "satisfaction_min": 70})
    # success 90 < 95 → breach
    qh.snapshot(_m(sr=90.0), 60.0)
    a = qh.assess_slo()
    assert a["status"]["success_rate"]["ok"] is False
    assert a["status"]["satisfaction"]["ok"] is False
    assert a["breaching"] is True


def test_drift_degrading_detected():
    qh = QualityHistory(tempfile.mktemp(suffix=".json"))
    # Inyectar puntos directamente (saltando el throttle) para simular el tiempo.
    pts = []
    for i in range(6):
        sat = 90 if i < 3 else 60   # cae de 90 a 60 → degrading
        pts.append({"t": i, "iso": "", "requests": 10, "success_rate": 99,
                    "p50": 800, "p95": 2000, "degradation_rate": 0, "satisfaction": sat})
    qh._write({"points": pts})
    a = qh.assess_slo()
    assert a["trend"]["satisfaction"]["direction"] == "degrading"
    assert a["trend"]["satisfaction"]["change_pct"] < 0
