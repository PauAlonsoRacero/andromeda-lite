<div align="center">

# 🌌 Andromeda Lite

**Local-first AI orchestration for your desktop  with a full MLOps lifecycle built in.**

Open source · Offline · Yours.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/PauAlonsoRacero/andromeda-lite/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Release](https://github.com/PauAlonsoRacero/andromeda-lite/actions/workflows/release.yml/badge.svg)](../../actions/workflows/release.yml)
![Tests](https://img.shields.io/badge/tests-160%20passing-brightgreen)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.12%2B-3776AB)
![Frontend](https://img.shields.io/badge/frontend-SolidJS-2C4F7C)
![Tests](https://img.shields.io/badge/tests-160%20passing-success)
![Security](https://img.shields.io/badge/bandit-0%20issues-success)

</div>

---

## Table of contents

1. [What is Andromeda Lite?](#1-what-is-andromeda-lite)
2. [The 30-second tour](#2-the-30-second-tour)
3. [System architecture](#3-system-architecture)
4. [How a single request flows](#4-how-a-single-request-flows)
5. [The MLOps lifecycle  the heart of the project](#5-the-mlops-lifecycle--the-heart-of-the-project)
6. [Feature map](#6-feature-map)
7. [MLOps maturity mapping](#7-mlops-maturity-mapping)
8. [Tech stack](#8-tech-stack)
9. [Project structure](#9-project-structure)
10. [Quick start](#10-quick-start)
11. [Testing, quality & security](#11-testing-quality--security)
12. [Design principles](#12-design-principles)

---

## 1. What is Andromeda Lite?

Andromeda Lite runs language models **entirely on your machine** through [Ollama](https://ollama.com)  no cloud, no token limits, no data leaving your computer. But it is more than a chat box on top of Ollama: it wraps a local model in a desktop app with **file access, tool use, an adaptive orchestrator, and a complete MLOps lifecycle** for evaluating, versioning, promoting and monitoring models in production.

> **In one line:** it's a local AI agent for everyone, *and* a working demonstration of the model lifecycle an MLOps engineer is responsible for  evaluation → registry → promotion → serving → monitoring → feedback → drift detection.

There are two faces to this project, and they're intentional:

| | What it shows |
|---|---|
| 🧑‍💻 **As a product** | A polished, offline desktop app anyone can install: pull a model, chat, give it files and tools. |
| 🛠️ **As an MLOps portfolio** | The full serving + experimentation + observability half of the ML lifecycle, implemented and running  not slides. |

---

## 2. The 30-second tour

- **100% local inference**  prompts and files never leave your machine. Works fully offline.
- **Adaptive orchestrator**  reads prompt complexity and scales the model's power level (low → ultra), capped by your hardware. Override any time.
- **Sandboxed file actions**  the AI reads, writes, moves and deletes files inside a workspace folder, through explicit, reversible action blocks.
- **MCP tools**  connect Model Context Protocol servers (filesystem, git, web…) with one click; the AI calls them on demand.
- **Model Registry + A/B testing + quality eval**  version models, promote the best to production, compare them in real use with statistical rigor, and watch quality drift over time against SLOs.
- **Plug-and-play models**  anything you `ollama pull` appears automatically. Zero config files.
- **Privacy-first**  incognito mode persists nothing; network egress is off by default.
- **Multilingual UI**  English, Spanish, German, Chinese, French.

---

## 3. System architecture

Andromeda Lite is a **single desktop process**: a native window (pywebview) hosting a SolidJS UI, an embedded FastAPI backend, and a thin client to a local Ollama server. No Docker, no accounts, no external services.

```mermaid
graph TB
    subgraph Desktop["Desktop app (one process)"]
        UI["SolidJS UI<br/>native window via pywebview"]
        API["FastAPI backend<br/>embedded, 127.0.0.1"]
        UI <-->|HTTP / SSE| API
    end

    API -->|HTTP localhost:11434| OLLAMA["Ollama<br/>local model inference"]
    API --> FS["Workspace folder<br/>sandboxed file actions"]
    API --> MCP["MCP servers<br/>filesystem - git - web"]
    API --> STORE["Local JSON / SQLite<br/>memory - registry - metrics - feedback"]

    OLLAMA --> MODELS["Local models<br/>llama3 - mistral - qwen"]

    style Desktop fill:#1a1d2e,stroke:#5b78f5,color:#fff
    style OLLAMA fill:#2a2140,stroke:#c87bd8,color:#fff
    style API fill:#16273a,stroke:#5b78f5,color:#fff
    style UI fill:#16273a,stroke:#34d399,color:#fff
```

**Why this shape?** Everything that matters runs locally and privately. The backend is embedded (not a separate server you manage), Ollama is the only dependency, and all state is plain files on your disk that you can inspect or delete.

---

## 4. How a single request flows

Lite uses **one** model and adapts its power, rather than running several at once. Here's what happens from the moment you hit Enter:

```mermaid
sequenceDiagram
    participant U as You
    participant F as Frontend
    participant B as Backend
    participant O as Orchestrator
    participant R as Model resolution
    participant L as Ollama

    U->>F: Type a prompt + hit Enter
    F->>B: POST /api/chat (stream)
    B->>O: Estimate prompt complexity
    O-->>B: Power level (low to ultra), capped by hardware
    B->>R: Which model serves this?
    Note over R: 1. Forced model?<br/>2. Active A/B experiment?<br/>3. Registry production model?<br/>4. Auto (power level)
    R-->>B: Resolved model
    B->>L: Stream generation
    L-->>B: Tokens (+ tool calls if needed)
    B-->>F: Server-Sent Events (live tokens)
    F-->>U: Streamed answer + feedback buttons
    Note over B: On completion: record metrics,<br/>A/B result, MLflow run, quality snapshot
```

The power-level decision is **deterministic and explainable**  the app shows you why it picked a level, and you can pin one manually.

| Prompt | Level |
|--------|-------|
| "thanks, that worked" | low |
| "explain how photosynthesis works" | mid |
| "refactor this function and analyze its time complexity" | high |
| "design a distributed system and prove its correctness step by step" | ultra |

---

## 5. The MLOps lifecycle  the heart of the project

This is what makes Andromeda more than a chat app. For a model-serving product, the MLOps lifecycle isn't about training  it's about **knowing which model to serve, proving it's better, and catching it when it gets worse**. Andromeda implements that whole loop, and the app actually *uses* it.

```mermaid
graph LR
    A["1. Evaluate<br/>golden set +<br/>LLM-as-judge"] --> B["2. Register<br/>version + score<br/>in registry"]
    B --> C["3. Promote<br/>staging to<br/>production"]
    C --> D["4. Serve<br/>app serves the<br/>production model"]
    D --> E["5. Monitor<br/>Prometheus +<br/>quality history"]
    E --> F["6. Feedback<br/>user votes +<br/>A/B testing"]
    F --> G{"7. Drift / SLO<br/>quality dropping?"}
    G -->|degrading| H["8. Roll back<br/>archive version,<br/>re-promote previous"]
    G -->|healthy| A
    H --> A

    style A fill:#16273a,stroke:#5b78f5,color:#fff
    style B fill:#16273a,stroke:#5b78f5,color:#fff
    style C fill:#1f3a2e,stroke:#34d399,color:#fff
    style D fill:#1f3a2e,stroke:#34d399,color:#fff
    style E fill:#2a2140,stroke:#c87bd8,color:#fff
    style F fill:#2a2140,stroke:#c87bd8,color:#fff
    style G fill:#3a2a1a,stroke:#f0a35f,color:#fff
    style H fill:#3a1a1a,stroke:#f0795f,color:#fff
```

### The loop, step by step

| Step | What it does | Where |
|------|--------------|-------|
| **1. Evaluate (offline)** | An LLM-as-judge scores a model 1–5 against a golden set across categories (factual, reasoning, code, safety…). Runs on demand or in CI. | `eval/quality_eval.py`, `eval/golden_set.jsonl` |
| **2. Register** | Save a model version with its eval score and notes. Auto-versioned (v1, v2…). | `backend/app/mlops/registry.py` |
| **3. Promote** | Move a version `staging → production`. Only one production version at a time  promoting another archives the previous. | `POST /api/registry/{id}/promote` |
| **4. Serve** | With *Serve production model* on, the chat serves exactly the promoted version (unless you force a model or an A/B is active). | `backend/app/routes/chat.py` |
| **5. Monitor** | Prometheus metrics (`/metrics`) + a quality time-series (success, latency, satisfaction) snapshotted every 5 min. | `backend/app/observability/`, `quality_history.py` |
| **6. Feedback & A/B** | 👍/👎 on each answer becomes a quality signal; A/B experiments compare two models in real traffic. | `backend/app/mlops/feedback.py`, `ab_testing.py` |
| **7. Drift & SLO** | The quality history compares recent vs. prior windows (improving/stable/degrading) and checks SLO thresholds (success ≥ 95%, p95 ≤ 8s, satisfaction ≥ 70%). | `backend/app/mlops/quality_history.py` |
| **8. Roll back** | If satisfaction drops, archive the version and re-promote the previous one  one-click rollback. | Model Registry UI |

### Statistical rigor, not vibes

The A/B testing doesn't declare a winner "by eye". It runs a **two-proportion z-test** and only calls a confident winner when there's enough sample **and** `p < 0.05`  on **both** success rate and user satisfaction (quality). Below that bar it shows a provisional leader and says so.

```mermaid
graph TD
    START["A/B experiment running"] --> Q{"Enough sample?<br/>30+ req / 20+ votes"}
    Q -->|No| LEAD["Show provisional leader<br/>keep collecting data"]
    Q -->|Yes| SIG{"z-test significant?<br/>p less than 0.05"}
    SIG -->|No| LEAD
    SIG -->|Yes| WIN["Confident winner<br/>by success AND quality"]

    style WIN fill:#1f3a2e,stroke:#34d399,color:#fff
    style LEAD fill:#3a2a1a,stroke:#f0a35f,color:#fff
```

---

## 6. Feature map

```mermaid
mindmap
  root((Andromeda Lite))
    Inference
      100% local via Ollama
      Adaptive power scaling
      Plug-and-play models
      Streaming SSE
    Agent capabilities
      Sandboxed file actions
      MCP tools
      Codex code mode
      Multimodal input
    MLOps
      Model Registry
      A/B testing z-test
      Quality eval golden set
      User feedback
      Drift and SLO monitoring
      MLflow tracking
    Ops and infra
      CI/CD GitHub Actions
      Kubernetes manifests
      Prometheus Grafana
      Security middleware
    Experience
      Memory across chats
      Incognito mode
      Multilingual UI
      In-app help
```

---

## 7. MLOps maturity mapping

For reviewers: here's how each piece maps to a recognized MLOps practice. Andromeda is a **serving/inference** product (not training), so the mapping covers the deployment-and-operations half of the lifecycle.

| MLOps practice | How Andromeda implements it |
|----------------|-----------------------------|
| **Experiment tracking** | MLflow integration logs runs with params (model, strategy, hardware tier) and metrics (latency, TTFT, success). |
| **Model registry & versioning** | First-class registry with `staging → production → archived` stages and exclusive production promotion. |
| **Continuous evaluation** | Golden-set + LLM-as-judge harness, runnable in CI as a quality gate before promotion. |
| **Online evaluation** | Per-response 👍/👎 feedback feeding satisfaction metrics and A/B variants. |
| **Experimentation** | A/B framework with two-proportion z-test and minimum-sample gating. |
| **Observability** | Prometheus exposition endpoint, Grafana dashboard, hand-rolled metrics with no heavy deps. |
| **Monitoring & alerting** | SLO thresholds + drift detection over a quality time-series; Prometheus alert rules. |
| **CI/CD** | GitHub Actions: tests, lint, frontend build, Docker build, security scan, k8s manifest validation. |
| **Infrastructure as code** | Full Kubernetes manifest set (Deployments, HPA, PDB, NetworkPolicy, ServiceMonitor) + Kustomize. |
| **Rollback strategy** | One-click archive + re-promote of the previous production model. |
| **Reproducibility** | Deterministic orchestration; pinned deps; config captured in MLflow runs. |
| **Security** | Localhost-only CORS allowlist, sandboxed execution, security middleware stack, `bandit` clean. |

> 📖 Deep-dive docs for the MLOps stack live in [`deploy/README.md`](deploy/README.md).

---

## 8. Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | SolidJS, Vite |
| Backend | FastAPI, Python 3.12, httpx |
| Inference | Ollama (local) |
| Desktop packaging | pywebview + PyInstaller (no Docker) |
| Experiment tracking | MLflow |
| Observability | Prometheus + Grafana |
| Orchestration | Kubernetes (+ Kustomize) |
| CI/CD | GitHub Actions |
| Security scanning | bandit, pip-audit |

---

## 9. Project structure

```
andromeda-lite/
├── backend/app/
│   ├── core/            # Orchestrator, flags, file actions, sandboxed subprocess
│   ├── hardware/        # Hardware detection + tier policy (VRAM/RAM aware)
│   ├── mcp/             # Model Context Protocol client + built-in tools
│   ├── memory/          # Semantic store + unified memory profile
│   ├── mlops/           # *** Registry, A/B testing, stats, feedback,
│   │                    #     quality history (drift/SLO), MLflow client
│   ├── observability/   # Metrics collector, tracer, Prometheus exposition
│   ├── routes/          # 27 API routers (chat, registry, ab, feedback, health…)
│   └── __init__.py      # App factory + lifespan (background tasks)
├── frontend/src/
│   ├── components/      # SolidJS UI (Chat, panels, charts, InfoButton…)
│   └── stores/          # State + i18n (5 languages)
├── eval/                # Golden set + LLM-as-judge harness
├── deploy/
│   ├── k8s/             # Kubernetes manifests + Kustomize
│   ├── monitoring/      # Prometheus, Grafana, alert rules
│   └── mlflow/          # MLflow tracking server
├── tests/               # 154 passing tests
├── .github/workflows/   # CI/CD pipelines
└── desktop.py           # Desktop entry point (pywebview + embedded backend)
```

---

## 10. Quick start

**Requirements:** [Ollama](https://ollama.com/download) installed and running. To build from source: Python 3.12+ and Node 18+.

```bash
# 1. Pull a model (any size your hardware can handle)
ollama pull llama3.2:3b       # light, fast  good starting point
# or: ollama pull qwen2.5:7b   # more capable, needs more VRAM

# 2. Clone
git clone https://github.com/PauAlonsoRacero/andromeda-lite.git
cd andromeda-lite

# 3a. Run from source  backend
cd backend
pip install -r requirements.txt
uvicorn app:create_app --factory --port 8000 &

# 3b. Run from source  frontend
cd ../frontend
npm install
npm run dev
```

Open the app, pick the model you pulled, and start chatting  the orchestrator handles the rest.

**On Windows**, the simplest path is the one-click `RUN-WINDOWS.bat` (no Docker, no build). Prebuilt binaries are attached to each [Release](../../releases).

### Try the MLOps loop in 2 minutes

```bash
# Evaluate a model against the golden set and register it with its score
python eval/quality_eval.py --model llama3.2:3b --judge qwen2.5:7b --register
```

Then open **Settings → Model Registry**, promote the version to *production*, toggle *Serve production model*, and chat  you're now serving the exact version you promoted. Watch **Analytics → Quality & SLO** as the satisfaction and latency series fill in.

---

## 11. Testing, quality & security

| Aspect | Status |
|--------|--------|
| Backend tests | **154 passing** (`pytest`) |
| Frontend build | 119 modules, clean |
| Static security scan | `bandit`  **0 medium+ issues** |
| Dependency audit | `pip-audit` in CI |
| Dead code | `pyflakes` clean in `backend/app` |
| CI gates | tests · lint · frontend build · Docker build · security · k8s validation |

```bash
# Run the test suite
PYTHONPATH=backend pytest tests/ -q

# Security scan
bandit -r backend/app -ll
```

**Security posture:** CORS is a localhost allowlist (never `*`), code execution is sandboxed (temp dir + timeout + restricted env), all subprocesses run windowless with no `shell=True` on untrusted input, there are no hardcoded secrets, and a middleware stack handles auth gating, security headers, rate limiting and request IDs.

---

## 12. Design principles

- **Local-first & private**  your data stays on your machine; network egress and telemetry are off by default.
- **Plug-and-play**  pull a model, it appears; no YAML to edit, no glue code.
- **Explainable**  the orchestrator shows *why* it chose a power level; the A/B shows *why* a model wins (with p-values).
- **Functional, not cosmetic**  the CI/CD, Kubernetes, monitoring and A/B pieces are real and tested, not scaffolding for show.
- **Honest about scope**  Andromeda serves and operates models; it doesn't train them. The MLOps story is the deployment-and-operations lifecycle, implemented end to end.

---

<div align="center">

**Andromeda Lite** is MIT-licensed and free forever. A commercial **Pro** edition (multi-model parallel orchestration, fine-tuning, multi-user, RAG) is in development.

Local-first AI, done right.

</div>
