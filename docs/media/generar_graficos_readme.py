"""Genera los gráficos del README (docs/media/*.png), en variante clara y oscura.

Solo usa datos medidos o contados en el propio repositorio:
  · memoria: salida de `python benchmarks/microbench.py` (500 / 2000 / 5000 recuerdos)
  · potencia: `_complexity_score` de backend/app/core/linear_orchestrator.py
  · cifras: tests, idiomas, conectores, skills, comandos y prompts del repo

Uso:  python docs/media/generar_graficos_readme.py      (necesita matplotlib)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent.parent / "backend"))

THEMES = {
    "dark":  dict(bg="#0B0E17", ink="#EAEEF7", sub="#8A93A8", grid="#222A3D",
                  base="#6B7488", accent="#6C8CFF",
                  bands=["#1B2236", "#1F2A47", "#26335C", "#2E3E72"]),
    "light": dict(bg="#FFFFFF", ink="#14181F", sub="#5B6475", grid="#E3E7EE",
                  base="#9AA3B5", accent="#2F5BEA",
                  bands=["#F1F4FA", "#E6ECFA", "#D9E3F8", "#CBDAF5"]),
}

# ── Datos ────────────────────────────────────────────────────────────────────
# microbench.py: ms por búsqueda (original → optimizado), 768 dimensiones.
MEM_N = [500, 2000, 5000]
MEM_ORIG = [152.3, 742.9, 1458.4]
MEM_NEW = [18.8, 93.9, 174.8]

PROMPTS = [  # (texto, puntuación real de _complexity_score)
    ("hola", None),
    ("crea una página index.html a partir de esta captura", None),
    ("Demuestra que la raíz de 2 es irracional", None),
    ("Diseña una arquitectura de microservicios con colas,\nidempotencia y reintentos, con código en Python", None),
]
STATS = [("1,257", "tests"), ("3", "sistemas en CI"), ("5", "idiomas"),
         ("10", "conectores MCP"), ("9", "skills"), ("13", "comandos /"),
         ("103", "prompts listos")]


def _style(t):
    plt.rcParams.update({
        "figure.facecolor": t["bg"], "axes.facecolor": t["bg"],
        "savefig.facecolor": t["bg"], "text.color": t["ink"],
        "axes.labelcolor": t["sub"], "xtick.color": t["sub"], "ytick.color": t["sub"],
        "font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
    })


def memoria(name, t):
    _style(t)
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=200)
    x = range(len(MEM_N)); w = 0.34
    ax.bar([i - w / 2 - 0.01 for i in x], MEM_ORIG, w, color=t["base"], label="Before (1.0 algorithm)")
    ax.bar([i + w / 2 + 0.01 for i in x], MEM_NEW, w, color=t["accent"], label="Andromeda 1.1")
    for i in x:
        ax.text(i - w / 2 - 0.01, MEM_ORIG[i] + 25, f"{MEM_ORIG[i]:,.0f} ms", ha="center", fontsize=9, color=t["sub"])
        ax.text(i + w / 2 + 0.01, MEM_NEW[i] + 25, f"{MEM_NEW[i]:,.0f} ms", ha="center", fontsize=9, color=t["ink"], weight="bold")
        ax.text(i + w / 2 + 0.01, MEM_NEW[i] + 150, f"{MEM_ORIG[i] / MEM_NEW[i]:.1f}×", ha="center", fontsize=11, color=t["accent"], weight="bold")
    ax.set_xticks(list(x)); ax.set_xticklabels([f"{n:,} memories" for n in MEM_N])
    ax.set_ylabel("Time per message (ms)"); ax.set_ylim(0, 1750)
    ax.yaxis.grid(True, color=t["grid"], lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(length=0)
    ax.legend(frameon=False, loc="upper left", labelcolor=t["ink"], fontsize=9)
    fig.suptitle("Memory search is ~8× faster", x=0.06, ha="left", fontsize=14, weight="bold", color=t["ink"])
    fig.text(0.06, 0.885, "Same results, measured with benchmarks/microbench.py (768-dim embeddings)",
             fontsize=9, color=t["sub"])
    fig.subplots_adjust(left=0.1, right=0.97, top=0.8, bottom=0.12)
    fig.savefig(OUT / f"chart-memory-speed-{name}.png"); plt.close(fig)


def potencia(name, t):
    from app.core import linear_orchestrator as lo
    pts = [(p, lo._complexity_score(p.replace("\n", " "))) for p, _ in PROMPTS]
    _style(t)
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=200)
    edges = [0, 0.22, 0.50, 0.66, 1.0]
    labels = ["Fast", "Balanced", "Strong", "Maximum"]
    for i in range(4):
        ax.axvspan(edges[i], edges[i + 1], color=t["bands"][i], lw=0)
        ax.text((edges[i] + edges[i + 1]) / 2, 4.55, labels[i], ha="center", fontsize=10,
                color=t["sub"], weight="bold")
    for k, (p, s) in enumerate(reversed(pts)):
        y = k + 0.55
        ax.plot([s], [y], "o", color=t["accent"], ms=9, mec=t["bg"], mew=2, zorder=3)
        side_right = s < 0.45
        ax.text(s + (0.025 if side_right else -0.025), y, f"{s:.2f}  {p}",
                ha="left" if side_right else "right", va="center", fontsize=8.6, color=t["ink"])
    ax.set_xlim(-0.03, 1); ax.set_ylim(0, 4.9); ax.set_yticks([])
    ax.set_xticks([0, 0.22, 0.5, 0.66, 1.0]); ax.set_xticklabels(["0", "0.22", "0.50", "0.66", "1"])
    ax.set_xlabel("Complexity score of the prompt")
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)
    fig.suptitle("Each message gets the power it needs", x=0.06, ha="left", fontsize=14, weight="bold", color=t["ink"])
    fig.text(0.06, 0.885, "Real scores from the router; thresholds cap at what your hardware can run",
             fontsize=9, color=t["sub"])
    fig.subplots_adjust(left=0.04, right=0.97, top=0.8, bottom=0.16)
    fig.savefig(OUT / f"chart-power-levels-{name}.png"); plt.close(fig)


def cifras(name, t):
    _style(t)
    fig, ax = plt.subplots(figsize=(10.5, 1.9), dpi=200)
    ax.axis("off"); ax.set_xlim(0, len(STATS)); ax.set_ylim(0, 1)
    eng = ["tests", "OS in CI", "languages", "MCP connectors", "skills", "/ commands", "ready prompts"]
    for i, ((num, _), lab) in enumerate(zip(STATS, eng)):
        ax.text(i + 0.5, 0.58, num, ha="center", va="center", fontsize=22, weight="bold", color=t["accent"])
        ax.text(i + 0.5, 0.22, lab, ha="center", va="center", fontsize=8.5, color=t["sub"])
    fig.savefig(OUT / f"chart-in-numbers-{name}.png", bbox_inches="tight", pad_inches=0.15); plt.close(fig)


if __name__ == "__main__":
    for n, t in THEMES.items():
        memoria(n, t); potencia(n, t); cifras(n, t)
    print("ok")
