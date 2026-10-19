"""Windows: selector de potencia con modelos antiguos, respuestas de un modelo
de programación, y rendimiento (nvidia-smi por mensaje, registro DEBUG)."""
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/src"


def _registro():
    from app.specialists.registry import SpecialistRegistry
    return SpecialistRegistry(str(ROOT / "config/specialists.yaml"))


def test_old_inherited_tiers_are_replaced_by_the_downloaded_pack():
    """Asignaciones de una versión antigua (deepseek-coder) nunca se sustituían."""
    from app.models.schemas import ModelLevel, ModelTiers
    r = _registro()
    viejo = ModelTiers()
    for lvl, m in (("low", "deepseek-coder:1.3b"), ("mid", "deepseek-coder:6.7b"), ("high", "deepseek-coder:6.7b")):
        setattr(viejo, lvl, ModelLevel(name=lvl, model_name=m, params_b=1, vram_required_gb=1,
                                       min_tier=1, description="Rápido"))
    r._tiers["generalist"] = viejo
    r.set_available_models(["deepseek-coder:1.3b", "deepseek-coder:6.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b"])
    t = r.get_tiers("generalist")
    assert (t.low.model_name, t.mid.model_name, t.high.model_name) == ("qwen3:4b", "qwen3:8b", "qwen3:14b")


def test_coding_models_only_when_nothing_else():
    from app.models.schemas import ModelTiers
    r = _registro()
    r._tiers["generalist"] = ModelTiers()
    r.set_available_models(["deepseek-coder:6.7b", "codellama:7b"])
    assert r.get_tiers("generalist").mid.model_name in ("deepseek-coder:6.7b", "codellama:7b")
    r.set_available_models(["deepseek-coder:6.7b", "codellama:7b", "gemma3:4b"])
    assert r.get_tiers("generalist").mid.model_name == "gemma3:4b"


def test_explicit_manual_assignment_is_still_respected():
    from app.models.schemas import ModelLevel, ModelTiers
    r = _registro()
    t = ModelTiers()
    t.mid = ModelLevel(name="mid", model_name="gemma3:4b", params_b=4, vram_required_gb=3,
                       min_tier=1, description=r._MANUAL_DESC)
    r._tiers["generalist"] = t
    r.set_available_models(["gemma3:4b", "qwen3:8b"])
    assert r.get_tiers("generalist").mid.model_name == "gemma3:4b"


def test_levels_refresh_after_download_and_on_request():
    src = (ROOT / "backend/app/routes/models.py").read_text(encoding="utf-8")
    assert "await refresh_available_models(request.app)       # lo recién descargado" in src
    i = src.index('if status == "success":')
    assert "refresh_available_models" in src[i:i + 300]


def test_nvidia_smi_is_not_run_on_every_message(monkeypatch):
    import app.hardware.detector as d
    llamadas = []

    def falso(cmd, **k):
        llamadas.append(cmd[0])
        return types.SimpleNamespace(returncode=0, stdout="12000\n")
    monkeypatch.setattr(d, "silent_run", falso)
    monkeypatch.setattr(d.sys, "platform", "win32")
    monkeypatch.setattr(d, "_NV_ULTIMO", {"v": None, "t": 0.0})
    monkeypatch.setattr(d, "_NV_HILO", object())        # sin hilo real en el test
    det = d.HardwareDetector()
    valores = [det.get_current_vram_free() for _ in range(15)]
    assert llamadas.count("nvidia-smi") == 1 and valores[-1] > 0


def test_packaged_app_logs_at_info():
    src = (ROOT / "backend/app/__init__.py").read_text(encoding="utf-8")
    assert 'if getattr(_sys, "frozen", False):\n        log_level = logging.INFO' in src
    assert "ANDROMEDA_LOG_LEVEL" in src


def test_lighter_effects_on_windows_and_paused_when_hidden():
    css = (SRC / "styles/index.css").read_text(encoding="utf-8")
    assert "body.os-win .bg-orb" in css and "body.app-hidden .bg-orb" in css
    app = (SRC / "App.jsx").read_text(encoding="utf-8")
    assert "classList.toggle('os-win'" in app and "visibilitychange" in app


def test_readme_no_longer_promises_manual_level_assignment():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "you can override any level in Settings" not in readme
