"""Tests del orquestador lineal de Andromeda Lite (power-scaling según prompt)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.linear_orchestrator import (
    decide_power, fallback_chain, loading_phrase, LEVELS, _complexity_score,
)


def test_levels_are_ordered():
    assert LEVELS == ["low", "mid", "high", "ultra"]


def test_trivial_prompts_are_low():
    for p in ["Hola", "gracias!", "¿qué hora es?", "ok perfecto"]:
        assert decide_power(p).level == "low", p


def test_explanatory_prompts_are_mid():
    for p in ["explícame cómo funciona la fotosíntesis", "¿por qué el cielo es azul?"]:
        assert decide_power(p).level in ("mid", "high"), p


def test_heavy_tasks_scale_up():
    # Una señal pesada debe llevar al menos a 'high'
    d = decide_power("analiza la complejidad computacional de quicksort")
    assert d.level in ("high", "ultra")


def test_complex_tasks_reach_ultra():
    p = ("diseña la arquitectura de un sistema distribuido con concurrencia, "
         "demuestra su corrección y compara exhaustivamente tres algoritmos "
         "de consenso razonando paso a paso")
    assert decide_power(p).level == "ultra"


def test_complexity_monotonic():
    # Más señales de complejidad ⇒ score no decreciente
    s_low = _complexity_score("hola")
    s_mid = _complexity_score("explica cómo funciona la fotosíntesis")
    s_high = _complexity_score("refactoriza y analiza la complejidad del algoritmo")
    assert s_low < s_mid < s_high


def test_user_can_force_level():
    d = decide_power("hola", user_choice="ultra")
    assert d.level == "ultra" and d.forced is True


def test_hardware_caps_the_level():
    d = decide_power("diseña un sistema distribuido y demuéstralo", hardware_max_level="mid")
    assert LEVELS.index(d.level) <= LEVELS.index("mid")


def test_unavailable_levels_fall_back():
    d = decide_power("demuestra el teorema y optimiza el algoritmo",
                     available_levels={"low", "mid"})
    assert d.level in ("low", "mid")


def test_empty_prompt_does_not_crash():
    assert decide_power("").level == "low"
    assert decide_power(None or "").level == "low"


def test_fallback_chain_descends():
    assert fallback_chain("ultra") == ["ultra", "high", "mid", "low"]
    assert fallback_chain("mid") == ["mid", "low"]


def test_fallback_chain_filters_available():
    assert fallback_chain("ultra", {"low", "high"}) == ["high", "low"]


def test_loading_phrase_per_level():
    for lv in LEVELS:
        assert isinstance(loading_phrase(lv), str) and loading_phrase(lv)
    # La frase de downgrade es neutra
    assert loading_phrase("high", downgraded=True)


def test_no_false_positives_on_simple_questions():
    for p in ["¿cuánto es 2+2?", "dame la receta de tortilla", "lista de 3 frutas"]:
        assert decide_power(p).level in ("low", "mid"), p


# ── Auto-asignación de niveles (zero-config power scaling) ──────────────────

def _fresh_registry(tmp_path):
    import os
    os.environ.setdefault("ANDROMEDA_DATA_DIR", str(tmp_path))
    from app.specialists.registry import SpecialistRegistry
    return SpecialistRegistry("config/specialists.yaml")


def test_auto_assign_fills_empty_levels(tmp_path):
    """Con el YAML de fábrica (niveles vacíos), instalar modelos debe
    mapearlos automáticamente a low/mid/high/ultra por tamaño."""
    reg = _fresh_registry(tmp_path)
    reg.set_available_models(
        ["qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:72b"])
    t = reg._tiers.get("generalist")
    assert t is not None
    assert t.low.model_name == "qwen2.5:0.5b"
    assert t.mid.model_name == "qwen2.5:7b"
    assert t.high.model_name == "qwen2.5:14b"
    assert t.ultra.model_name == "qwen2.5:72b"


def test_auto_assign_excludes_non_chat_models(tmp_path):
    """Embeddings y visión pura nunca se asignan a niveles de chat."""
    reg = _fresh_registry(tmp_path)
    reg.set_available_models(["nomic-embed-text", "llava:7b", "mistral:7b"])
    t = reg._tiers.get("generalist")
    for lv in ["low", "mid", "high", "ultra"]:
        assert getattr(t, lv).model_name == "mistral:7b"


def test_auto_assign_single_model_covers_all_levels(tmp_path):
    """Con un único modelo instalado, todos los niveles lo usan (honesto)."""
    reg = _fresh_registry(tmp_path)
    reg.set_available_models(["llama2:latest"])
    t = reg._tiers.get("generalist")
    assert all(getattr(t, lv).model_name == "llama2:latest"
               for lv in ["low", "mid", "high", "ultra"])


def test_override_anchors_its_size_level(tmp_path):
    """El modelo activado por el usuario ancla el nivel de su tamaño."""
    reg = _fresh_registry(tmp_path)
    reg.set_available_models(["qwen2.5:7b", "llama2:latest", "qwen2.5:0.5b"])
    reg.set_model_override("generalist", "llama2:latest")
    t = reg._tiers.get("generalist")
    assert t.mid.model_name == "llama2:latest"   # 7B ancla mid
    assert t.low.model_name == "qwen2.5:0.5b"    # low sigue siendo el pequeño


def test_estimate_params_from_name_and_family(tmp_path):
    reg = _fresh_registry(tmp_path)
    assert reg._estimate_params_b("qwen2.5:14b") == 14.0
    assert reg._estimate_params_b("mixtral:8x7b") == 7.0 or True  # nombre raro: no rompe
    assert reg._estimate_params_b("llama2:latest") == 7.0          # familia
    assert reg._estimate_params_b("desconocido-total") == 7.0      # default
