"""test_pipeline.py — Tests de integración completos de Andromeda."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# ── Health ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_valid(app_client):
    r = await app_client.get("/api/health")
    assert r.status_code in (200, 503)
    d = r.json()
    assert d["status"] in ("ok", "degraded", "down")
    assert "specialists" in d

@pytest.mark.asyncio
async def test_hardware_tier(app_client):
    r = await app_client.get("/api/health/hardware")
    assert r.status_code == 200
    d = r.json()
    assert 1 <= d["max_tier"] <= 4
    assert d["acceleration"] in ("cuda", "rocm", "metal", "cpu")

@pytest.mark.asyncio
async def test_policy_endpoint(app_client):
    r = await app_client.get("/api/health/policy")
    assert r.status_code == 200
    d = r.json()
    assert "max_parallel" in d
    assert "eligible_strategies" in d

@pytest.mark.asyncio
async def test_vram_plan(app_client):
    r = await app_client.get("/api/health/vram-plan")
    assert r.status_code == 200
    d = r.json()
    assert "plans" in d
    assert all(str(n) in d["plans"] for n in [1,2,3,4])

# ── Models ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skip(reason="Funcionalidad de Pro (6 especialistas / MLOps)")
async def test_models_at_least_six(app_client):
    r = await app_client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()["specialists"]) >= 6

@pytest.mark.asyncio
async def test_models_status(app_client):
    r = await app_client.get("/api/models/status")
    assert r.status_code == 200
    assert "ollama_reachable" in r.json()

@pytest.mark.asyncio
@pytest.mark.skip(reason="Funcionalidad de Pro (6 especialistas / MLOps)")
async def test_model_levels(app_client):
    r = await app_client.get("/api/models/levels/software-engineering")
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_update_nonexistent_model_404(app_client):
    r = await app_client.put("/api/models/nope", json={"model_name":"x","active":True})
    assert r.status_code == 404
    assert r.json()["error"] is True

@pytest.mark.asyncio
async def test_warm_status(app_client):
    r = await app_client.get("/api/models/warm-status")
    assert r.status_code == 200
    assert "configured_warm" in r.json()

# ── Chat ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_no_prompt_422(app_client):
    r = await app_client.post("/api/chat", json={"strategy":"single"})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"

@pytest.mark.asyncio
async def test_chat_empty_prompt_422(app_client):
    r = await app_client.post("/api/chat", json={"prompt":"","stream":False})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_chat_strategies(app_client):
    r = await app_client.get("/api/chat/strategies")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["strategies"]}
    assert "single" in ids
    assert "iterative_refine" in ids

@pytest.mark.asyncio
async def test_prompts_crud(app_client):
    # Create
    r = await app_client.post("/api/chat/prompts",
        json={"title":"T","content":"Explain Docker"})
    assert r.json()["success"] is True
    pid = r.json()["id"]
    # List
    r = await app_client.get("/api/chat/prompts")
    assert any(p["id"]==pid for p in r.json()["prompts"])
    # Use
    r = await app_client.post(f"/api/chat/prompts/{pid}/use")
    assert r.json()["success"] is True
    # Delete
    r = await app_client.delete(f"/api/chat/prompts/{pid}")
    assert r.json()["success"] is True

# ── Traces ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_traces_list(app_client):
    r = await app_client.get("/api/traces")
    assert r.status_code == 200
    assert isinstance(r.json()["traces"], list)

@pytest.mark.asyncio
async def test_traces_limit(app_client):
    r = await app_client.get("/api/traces?limit=3")
    assert len(r.json()["traces"]) <= 3

@pytest.mark.asyncio
async def test_trace_not_found(app_client):
    r = await app_client.get("/api/traces/nonexistent-id")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_metrics_structure(app_client):
    r = await app_client.get("/api/traces/metrics")
    d = r.json()
    assert "realtime" in d
    assert "historical" in d

# ── MLOps ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.skip(reason="Funcionalidad de Pro (6 especialistas / MLOps)")
async def test_mlops_summary(app_client):
    r = await app_client.get("/api/mlops/summary")
    assert r.status_code == 200
    # Can have either mlflow_enabled (mlflow active) or total_runs (sqlite only)
    d = r.json()
    assert "total_runs" in d or "mlflow_enabled" in d

@pytest.mark.asyncio
@pytest.mark.skip(reason="Funcionalidad de Pro (6 especialistas / MLOps)")
async def test_mlops_runs(app_client):
    r = await app_client.get("/api/mlops/runs")
    assert r.status_code == 200
    assert "runs" in r.json()

# ── MCP ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_status(app_client):
    r = await app_client.get("/api/mcp/status")
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_mcp_tools(app_client):
    r = await app_client.get("/api/mcp/tools")
    assert r.status_code == 200
    assert isinstance(r.json()["tools"], list)

# ── Sandbox ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_langs(app_client):
    r = await app_client.get("/api/sandbox/langs")
    langs = {l["id"] for l in r.json()["languages"]}
    assert "python" in langs

@pytest.mark.asyncio
async def test_sandbox_hello_world(app_client):
    r = await app_client.post("/api/sandbox/run",
        json={"code":"print('hello andromeda')","language":"python","timeout":10})
    d = r.json()
    assert d["success"] is True
    assert "hello andromeda" in d["stdout"]
    assert d["exit_code"] == 0

@pytest.mark.asyncio
async def test_sandbox_syntax_error(app_client):
    r = await app_client.post("/api/sandbox/run",
        json={"code":"def bad(:","language":"python","timeout":10})
    d = r.json()
    assert d["success"] is False
    assert d["exit_code"] != 0

@pytest.mark.asyncio
async def test_sandbox_loop(app_client):
    r = await app_client.post("/api/sandbox/run",
        json={"code":"for i in range(3): print(i)","language":"python","timeout":10})
    d = r.json()
    assert d["success"] is True
    assert "0\n1\n2" in d["stdout"]

@pytest.mark.asyncio
async def test_sandbox_check_high_risk(app_client):
    r = await app_client.post("/api/sandbox/check",
        json={"code":"exec('x')\neval('y')\n__import__('os')","language":"python"})
    d = r.json()
    assert d["risk"] == "high"
    assert not d["safe_to_run"]

@pytest.mark.asyncio
async def test_sandbox_check_safe(app_client):
    r = await app_client.post("/api/sandbox/check",
        json={"code":"result = sum(range(10))\nprint(result)","language":"python"})
    d = r.json()
    assert d["risk"] == "low"
    assert d["safe_to_run"] is True

@pytest.mark.asyncio
async def test_sandbox_empty_code_400(app_client):
    r = await app_client.post("/api/sandbox/run",
        json={"code":"","language":"python"})
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_sandbox_unsupported_lang_400(app_client):
    r = await app_client.post("/api/sandbox/run",
        json={"code":"puts 'hi'","language":"ruby"})
    # 400 si el lenguaje no está en la lista; 503 si está pero no hay runtime.
    # Ambos son respuestas correctas a "no puedo ejecutar esto".
    assert r.status_code in (400, 503)

# ── Context ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_empty(app_client):
    await app_client.delete("/api/context")
    r = await app_client.get("/api/context/summary")
    assert r.json()["indexed"] is False

@pytest.mark.asyncio
async def test_context_invalid_path_404(app_client):
    r = await app_client.post("/api/context/index",
        json={"path":"/this/path/does/not/exist/xyz999"})
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_context_index_and_summary(app_client, tmp_path):
    (tmp_path/"main.py").write_text("def hello(): return 'world'")
    (tmp_path/"README.md").write_text("# Test\nA project.")
    r = await app_client.post("/api/context/index", json={"path":str(tmp_path)})
    assert r.json()["success"] is True
    assert r.json()["files_indexed"] == 2
    r = await app_client.get("/api/context/summary")
    assert r.json()["indexed"] is True
    await app_client.delete("/api/context")

@pytest.mark.asyncio
async def test_context_query_without_index_400(app_client):
    await app_client.delete("/api/context")
    r = await app_client.post("/api/context/query",
        json={"question":"What does this do?"})
    assert r.status_code == 400

# ── Memory ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_stats(app_client):
    r = await app_client.get("/api/memory/stats")
    assert r.status_code == 200

@pytest.mark.asyncio
async def test_memory_search(app_client):
    r = await app_client.get("/api/memory/search?q=docker")
    assert r.status_code == 200
    assert "results" in r.json()

# ── Vision ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vision_models(app_client):
    r = await app_client.get("/api/vision/models")
    assert r.status_code == 200
    assert "models" in r.json()

@pytest.mark.asyncio
async def test_vision_no_image_400(app_client):
    r = await app_client.post("/api/vision/analyze",
        json={"question":"What is this?"})
    assert r.status_code == 400

# ── ADR ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adr_templates(app_client):
    r = await app_client.post("/api/adr/list-templates")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["templates"]}
    assert "framework" in ids

@pytest.mark.asyncio
async def test_adr_no_decision_400(app_client):
    r = await app_client.post("/api/adr/generate", json={"context":"x"})
    assert r.status_code == 400

# ── Alerts ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alerts_list(app_client):
    r = await app_client.get("/api/alerts")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["alerts"], list)
    assert "count" in d

@pytest.mark.asyncio
async def test_alerts_config(app_client):
    r = await app_client.get("/api/alerts/config")
    assert r.status_code == 200
    assert "vram_pct" in r.json()
    r = await app_client.put("/api/alerts/config", json={"vram_pct": 90.0})
    assert r.json()["config"]["vram_pct"] == 90.0

# ══════════════════════════════════════════════════════════════════════════
# UNIT TESTS
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="Clasificador multi-IA es exclusivo de Pro")
def test_classifier_coding():
    from app.core.classifier import _classify_with_keywords
    from app.models.schemas import HardwarePolicy
    p = HardwarePolicy(tier=2,max_parallel=2,recommended_quant="Q5",
        max_context_tokens=4096,strategy_budget="balanced",
        can_run_verifier=True,safe_vram_threshold_gb=6.0,
        eligible_strategies=["single","iterative_refine"])
    r = _classify_with_keywords(
        "Fix this Python TypeError", ["software-engineering","generalist"], p)
    assert "software-engineering" in r["specialists"]
    assert r["confidence"] > 0.3

@pytest.mark.skip(reason="Clasificador multi-IA es exclusivo de Pro")
def test_classifier_itops():
    from app.core.classifier import _classify_with_keywords
    from app.models.schemas import HardwarePolicy
    p = HardwarePolicy(tier=2,max_parallel=2,recommended_quant="Q5",
        max_context_tokens=4096,strategy_budget="balanced",
        can_run_verifier=True,safe_vram_threshold_gb=6.0,
        eligible_strategies=["single"])
    r = _classify_with_keywords(
        "Configure nginx reverse proxy Docker", ["it-ops","generalist"], p)
    assert "it-ops" in r["specialists"]

@pytest.mark.skip(reason="Clasificador multi-IA es exclusivo de Pro")
def test_classifier_fallback():
    from app.core.classifier import _classify_with_keywords
    from app.models.schemas import HardwarePolicy
    p = HardwarePolicy(tier=1,max_parallel=1,recommended_quant="Q4",
        max_context_tokens=2048,strategy_budget="conservative",
        can_run_verifier=False,safe_vram_threshold_gb=2.0,
        eligible_strategies=["single"])
    r = _classify_with_keywords(
        "Hello how are you?", ["software-engineering","generalist"], p)
    assert r["specialists"] == ["generalist"]

def test_policy_t1_limits():
    from app.hardware.policy import PolicyEngine
    from app.models.schemas import HardwareInfo
    engine = PolicyEngine("config/hardware_policies.yaml")
    hw = HardwareInfo(os="Linux",cpu_model="x",cpu_cores=4,
        ram_total_gb=16.0,ram_available_gb=8.0,gpus=[],
        total_vram_gb=0.0,acceleration="cpu",max_tier=1)
    pol = engine.get_policy(hw)
    assert pol.max_parallel == 1
    assert "quality_first" not in pol.eligible_strategies

def test_policy_t2_verifier():
    from app.hardware.policy import PolicyEngine
    from app.models.schemas import HardwareInfo
    engine = PolicyEngine("config/hardware_policies.yaml")
    hw = HardwareInfo(os="Linux",cpu_model="x",cpu_cores=8,
        ram_total_gb=32.0,ram_available_gb=16.0,gpus=[],
        total_vram_gb=16.0,acceleration="cuda",max_tier=2)
    pol = engine.get_policy(hw)
    assert pol.max_parallel >= 2
    assert pol.can_run_verifier is True

def test_hardware_detector_no_crash():
    from app.hardware.detector import HardwareDetector
    info = HardwareDetector().detect()
    assert 1 <= info.max_tier <= 4

def test_model_tiers_logic():
    from app.models.schemas import ModelLevel, ModelTiers
    tiers = ModelTiers(
        low=ModelLevel(name="low",model_name="m:3b",params_b=3,
            vram_required_gb=3.0,min_tier=1),
        mid=ModelLevel(name="mid",model_name="m:7b",params_b=7,
            vram_required_gb=6.0,min_tier=1),
        high=ModelLevel(name="high",model_name="m:14b",params_b=14,
            vram_required_gb=12.0,min_tier=2),
    )
    assert tiers.best_for_tier(1, 8.0).name == "mid"
    assert tiers.best_for_tier(2, 14.0).name == "high"
    assert tiers.best_for_tier(1, 4.0).name == "low"
    assert tiers.best_for_tier(1, 1.0) is None

def test_cosine_similarity():
    from app.memory.store import SemanticMemoryStore
    sim = SemanticMemoryStore._cosine_similarity
    assert abs(sim([1.0,0.0],[1.0,0.0]) - 1.0) < 1e-6
    assert abs(sim([1.0,0.0],[0.0,1.0]) - 0.0) < 1e-6
    assert abs(sim([1.0,0.0],[-1.0,0.0]) - (-1.0)) < 1e-6
    assert sim([],[]) == 0.0

def test_memory_classify_category():
    from app.memory.store import SemanticMemoryStore
    c = SemanticMemoryStore._classify_category
    assert c("Fix Python bug with asyncio") == "code"
    assert c("Configure Docker and nginx") in ("devops", "general")
    assert c("PostgreSQL query optimization") == "database"
    assert c("Microservices architecture design pattern") in ("architecture", "general")
    assert c("Good morning!") == "general"

def test_memory_importance():
    from app.memory.store import SemanticMemoryStore
    est = SemanticMemoryStore._estimate_importance
    short = est("hi","ok")
    long_code = est("fix","Here:\n```python\n"+"x=1\n"*50+"```\nThis works.")
    assert long_code > short
    assert 0.0 <= short <= 1.0
