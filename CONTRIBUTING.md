# Contributing to Andromeda Lite

Thanks for your interest. Andromeda Lite is open source (MIT) and contributions are welcome.

## Reporting bugs

Open an issue with:
- Your OS and version (macOS 14, Windows 11, etc.)
- The model you were using (e.g. `llama3.2:3b`)
- Steps to reproduce
- What you expected vs. what happened

The app has a self-diagnosis endpoint at `GET /api/health/diagnose` — its output is very helpful in bug reports.

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep changes focused — one feature or fix per PR.
3. Make sure the backend compiles (`python -m compileall app`) and the frontend builds (`npm run build`).
4. Describe what the change does and why.

## Scope

This repository is **Andromeda Lite** — the free, single-model edition. Multi-AI orchestration, fine-tuning and the MLOps dashboard belong to the commercial Pro edition and are not part of this repo, so PRs adding those won't be merged here. Improvements to the local inference experience, the linear orchestrator, file actions, MCP integration, UI and docs are all fair game.

## Code style

- Backend: clear, typed Python. Keep functions small and explain non-obvious logic in comments.
- Frontend: SolidJS idioms, no heavy dependencies without discussion.

## License

By contributing you agree your contributions are licensed under the MIT License.
