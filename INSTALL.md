# Andromeda Lite — Installation

> **Just want to use it?** Grab the installer for your OS from the
> [Releases page](../../releases) — it sets up everything (Ollama included on
> Windows). This document is for running from source or Docker.

Two ways to run Andromeda Lite: **Docker** (recommended, everything in containers) or **from source** (for development). In both cases, Ollama runs on your host machine.

## Requirements

- [Ollama](https://ollama.com) installed and running on your machine
- For Docker: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- For source: Python 3.12+ and Node 18+
- A machine that can run a local model. CPU-only works but is slow; a GPU with 8 GB+ VRAM is recommended.

---

## Option A — Docker (recommended)

### 1. Pull a model with Ollama

```bash
ollama pull llama3.2:3b      # light, fast — good starting point
# or, if you have more VRAM:
ollama pull mistral:7b
```

### 2. Clone and start

```bash
git clone https://github.com/PauAlonsoRacero/andromeda-lite.git
cd andromeda-lite
docker compose up -d
```

Docker builds the backend and frontend and starts them. The backend reaches Ollama on your host through `host.docker.internal`.

### 3. Open the app

Go to `http://localhost` in your browser. Pick the model you pulled and start chatting.

To stop: `docker compose down`.

---

## Option B — From source (development)

### 1. Pull a model

```bash
ollama pull llama3.2:3b
```

### 2. Backend

```bash
cd andromeda-lite/backend
pip install -r requirements.txt
uvicorn app:create_app --factory --port 8000
```

### 3. Frontend (in another terminal)

```bash
cd andromeda-lite/frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`).

---

## How models work

Andromeda Lite uses a single model (the "generalist") with **four power levels** (low / mid / high / ultra). The linear orchestrator picks the level automatically based on the complexity of your prompt, capped by what your hardware can run and which models you've actually pulled.

You can map each level to a different model in `config/specialists.yaml`, or just pull one model and let it handle everything. Anything you `ollama pull` is detected automatically — no need to edit config files for a model to appear.

---

## Troubleshooting

- **"Ollama not reachable"** — make sure `ollama serve` is running (`ollama list` should work). On Docker, the backend expects Ollama on the host at port 11434.
- **The app loads but answers fail** — check `GET /api/health/diagnose`, which reports each part of the chain (Ollama, models, specialists).
- **Slow responses on CPU** — that's expected without a GPU. Use a smaller model like `llama3.2:3b`.

For more detail, see the [README](README.md).
