"""Tests del feedback de usuario, la calidad en A/B y el parser del juez."""
import sys, tempfile
sys.path.insert(0, "backend")
sys.path.insert(0, "eval")
from app.mlops.feedback import FeedbackStore
from app.mlops.ab_testing import ABTesting


def test_feedback_store_counts_and_satisfaction():
    fb = FeedbackStore(tempfile.mktemp(suffix=".json"))
    fb.record("r1", True, model="mistral:7b")
    fb.record("r2", True)
    fb.record("r3", False)
    s = fb.stats()
    assert s["up"] == 2 and s["down"] == 1
    assert s["total"] == 3
    assert s["satisfaction"] == 66.7
    assert len(s["recent"]) == 3


def test_ab_quality_signal_feeds_variant():
    ab = ABTesting(tempfile.mktemp(suffix=".json"))
    ab.create("x", [{"name": "A", "model": "a", "weight": 50},
                    {"name": "B", "model": "b", "weight": 50}])
    # A recibe buen feedback, B malo.
    for _ in range(8):
        ab.record_quality("x", "A", True)
    ab.record_quality("x", "A", False)        # A: 8/9
    for _ in range(7):
        ab.record_quality("x", "B", False)
    ab.record_quality("x", "B", True)         # B: 1/8
    res = ab.results("x")
    assert res["variants"]["A"]["ratings"] == 9
    assert res["variants"]["A"]["satisfaction"] == round(8/9*100, 1)
    assert res["variants"]["B"]["satisfaction"] == round(1/8*100, 1)


def test_ab_satisfaction_none_without_feedback():
    ab = ABTesting(tempfile.mktemp(suffix=".json"))
    ab.create("x", [{"name": "A", "model": "a", "weight": 50},
                    {"name": "B", "model": "b", "weight": 50}])
    res = ab.results("x")
    assert res["variants"]["A"]["satisfaction"] is None


def test_judge_score_parser():
    from quality_eval import _parse_score
    # JSON limpio
    s, r = _parse_score('{"score": 4, "reason": "buena pero incompleta"}')
    assert s == 4 and "incompleta" in r
    # JSON embebido en texto
    s, _ = _parse_score('Mi veredicto:\n{"score": 5, "reason": "perfecta"}\nGracias')
    assert s == 5
    # Número suelto sin JSON
    s, _ = _parse_score('Le doy un 3 sobre 5')
    assert s == 3
    # Clamp fuera de rango
    s, _ = _parse_score('{"score": 9}')
    assert s == 5


def test_quality_verdict_picks_satisfaction_winner():
    """El veredicto de calidad debe declarar ganador con muestra y significancia."""
    from app.mlops.stats import assess_quality
    variants = {
        "A": {"requests": 50, "successes": 50, "ratings": 40, "positive": 36},  # 90%
        "B": {"requests": 50, "successes": 50, "ratings": 40, "positive": 20},  # 50%
    }
    v = assess_quality(variants)
    assert v["quality_enough_sample"] is True
    assert v["quality_winner"] == "A"
    assert v["quality_confident"] is True
    assert v["quality_test"]["significant"] is True


def test_quality_verdict_needs_enough_votes():
    """Con pocos votos no declara ganador aunque haya diferencia."""
    from app.mlops.stats import assess_quality
    variants = {
        "A": {"requests": 5, "successes": 5, "ratings": 3, "positive": 3},
        "B": {"requests": 5, "successes": 5, "ratings": 3, "positive": 0},
    }
    v = assess_quality(variants)
    assert v["quality_enough_sample"] is False
    assert v["quality_winner"] is None
    assert v.get("quality_leader") == "A"
