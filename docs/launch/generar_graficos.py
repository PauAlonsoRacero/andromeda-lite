"""
Genera gráficos comparativos de Andromeda vs IAs/programas similares.

IMPORTANTE — honestidad: NO inventamos números de "calidad de respuesta"
comparando con GPT/Claude (sería indefendible y dañaría credibilidad). Solo
comparamos en dimensiones VERIFICABLES y estructurales donde la comparación es
un hecho, no una opinión: privacidad, coste, límites, ejecución local, open
source. Ahí es donde Andromeda gana de verdad.

Salida: PNGs de alta resolución listos para LinkedIn y README de GitHub.
"""

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.font_manager as fm
import numpy as np

# ── Paleta Andromeda (espacio / nebulosa) ─────────────────────────────────────
BG        = "#0B0E17"   # azul casi negro (fondo espacio)
PANEL     = "#141A2A"   # panel
ACCENT    = "#6C8CFF"   # azul Andromeda
ACCENT2   = "#B98CFF"   # violeta nebulosa
GOOD      = "#3FD08A"   # verde (ventaja)
BAD       = "#FF6B6B"   # rojo (desventaja)
WARN      = "#FFC857"   # ámbar (parcial)
TEXT      = "#EAEEF7"
MUTED     = "#8A93A8"
GRID      = "#222A3D"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "font.size": 12,
    "font.family": "DejaVu Sans",
})


# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 1 — Tabla comparativa de características (la más fuerte para LinkedIn)
# ══════════════════════════════════════════════════════════════════════════════
def chart_feature_matrix(path: str):
    productos = ["Andromeda", "ChatGPT", "Claude", "Gemini", "Ollama\n(solo)"]
    criterios = [
        "100% local / privado",
        "Sin enviar datos a la nube",
        "Sin límite de tokens",
        "Coste mensual = 0€",
        "Código abierto",
        "Orquestación multi-IA local",
        "Acceso a archivos local",
        "Funciona sin internet",
    ]
    # 2 = sí (verde), 1 = parcial (ámbar), 0 = no (rojo)
    M = np.array([
        # Andr  GPT  Claude Gem  Ollama
        [2,     0,   0,     0,   2],   # local/privado
        [2,     0,   0,     0,   2],   # sin nube
        [2,     0,   0,     0,   2],   # sin límite tokens
        [2,     0,   0,     0,   2],   # coste 0
        [2,     0,   0,     0,   2],   # open source
        [2,     0,   0,     0,   0],   # orquestación multi-IA
        [2,     1,   1,     0,   0],   # acceso a archivos
        [2,     0,   0,     0,   2],   # offline
    ])

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, len(productos))
    ax.set_ylim(0, len(criterios))
    color_map = {2: GOOD, 1: WARN, 0: BAD}
    symbol_map = {2: "✓", 1: "~", 0: "✕"}

    for i, crit in enumerate(criterios):
        y = len(criterios) - 1 - i
        for j, _ in enumerate(productos):
            v = M[i, j]
            cell = FancyBboxPatch(
                (j + 0.07, y + 0.12), 0.86, 0.76,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                linewidth=0, facecolor=color_map[v], alpha=0.92, zorder=2)
            ax.add_patch(cell)
            ax.text(j + 0.5, y + 0.5, symbol_map[v], ha="center", va="center",
                    fontsize=20, color="#0B0E17", fontweight="bold", zorder=3)

    # etiquetas de criterios (izquierda)
    for i, crit in enumerate(criterios):
        y = len(criterios) - 1 - i
        ax.text(-0.15, y + 0.5, crit, ha="right", va="center",
                fontsize=12.5, color=TEXT)

    # cabeceras de productos (arriba)
    for j, prod in enumerate(productos):
        col = ACCENT if prod == "Andromeda" else MUTED
        weight = "bold" if prod == "Andromeda" else "normal"
        ax.text(j + 0.5, len(criterios) + 0.15, prod, ha="center", va="bottom",
                fontsize=13, color=col, fontweight=weight)

    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    fig.suptitle("Andromeda  vs  IAs en la nube",
                 fontsize=22, fontweight="bold", color=TEXT, x=0.5, y=0.99)
    ax.text(len(productos) / 2, -0.9,
            "Comparación de características estructurales · "
            "✓ sí    ~ parcial    ✕ no",
            ha="center", fontsize=11, color=MUTED)

    plt.subplots_adjust(left=0.28, right=0.97, top=0.90, bottom=0.10)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {path}")


# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 2 — Coste anual (hecho verificable y muy visual)
# ══════════════════════════════════════════════════════════════════════════════
def chart_cost(path: str):
    productos = ["Andromeda", "ChatGPT Plus", "Claude Pro", "Gemini\nAdvanced"]
    coste_anual = [0, 12 * 23, 12 * 22, 12 * 22]   # ~€/año aprox. planes consumer
    colores = [GOOD, MUTED, MUTED, MUTED]

    fig, ax = plt.subplots(figsize=(11, 6.5))
    bars = ax.bar(productos, coste_anual, color=colores, width=0.6, zorder=3,
                  edgecolor=BG, linewidth=2)
    bars[0].set_color(ACCENT)

    for b, v in zip(bars, coste_anual):
        ax.text(b.get_x() + b.get_width() / 2, v + 6,
                ("0 €" if v == 0 else f"~{v} €"),
                ha="center", va="bottom", fontsize=14, fontweight="bold",
                color=(GOOD if v == 0 else TEXT))

    ax.set_ylabel("Coste por usuario / año (€)", fontsize=13)
    ax.set_title("Coste anual: suscripción en la nube vs ejecución local",
                 fontsize=18, fontweight="bold", pad=18)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(GRID)
    ax.set_ylim(0, max(coste_anual) * 1.2)
    ax.text(0.5, -0.16,
            "Andromeda corre en tu propio hardware: la inferencia local "
            "no tiene coste de suscripción.\nLas cifras de la nube son planes "
            "de consumo orientativos (2026).",
            transform=ax.transAxes, ha="center", fontsize=10, color=MUTED)

    plt.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {path}")


# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 3 — Cómo funciona la orquestación (el diferenciador técnico)
# ══════════════════════════════════════════════════════════════════════════════
def chart_orchestration(path: str):
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(0, 12); ax.set_ylim(0, 7)
    ax.axis("off")

    def box(x, y, w, h, label, color, sub=""):
        b = FancyBboxPatch((x, y), w, h,
                           boxstyle="round,pad=0.04,rounding_size=0.15",
                           linewidth=2, edgecolor=color, facecolor=PANEL, zorder=2)
        ax.add_patch(b)
        ax.text(x + w / 2, y + h / 2 + (0.18 if sub else 0), label,
                ha="center", va="center", fontsize=12, color=TEXT,
                fontweight="bold", zorder=3)
        if sub:
            ax.text(x + w / 2, y + h / 2 - 0.32, sub, ha="center", va="center",
                    fontsize=9.5, color=MUTED, zorder=3)

    def arrow(x1, y1, x2, y2, color=ACCENT):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=2.2))

    # Prompt
    box(0.3, 3, 2, 1.2, "Pregunta", ACCENT2, "del usuario")
    # Orquestador
    box(3, 2.9, 2.2, 1.4, "Orquestador", ACCENT,
        "detecta dominio\n+ complejidad")
    arrow(2.3, 3.6, 3, 3.6)

    # Especialistas en paralelo
    specs = [
        ("Código", 5.7), ("Razona-\nmiento", 4.3),
        ("Escritura", 2.9), ("Factual", 1.5),
    ]
    for name, y in specs:
        box(6.1, y, 1.8, 1.1, name, ACCENT2)
        arrow(5.2, 3.6, 6.1, y + 0.55)

    # Fusionador
    box(8.6, 2.9, 2.0, 1.4, "Fusionador", GOOD, "sintetiza la\nmejor respuesta")
    for _, y in specs:
        arrow(7.9, y + 0.55, 8.6, 3.6)

    # Respuesta
    box(8.9, 0.5, 1.8, 1.0, "Respuesta", ACCENT2, "")
    arrow(9.6, 2.9, 9.7, 1.5)

    ax.set_title("Andromeda Orquesta · enrutamiento adaptativo + fusión multi-IA",
                 fontsize=17, fontweight="bold", pad=10)
    ax.text(6, 0.1,
            "El orquestador elige el especialista y el tamaño de modelo según la "
            "tarea · 96 % de acierto en 75 casos de prueba",
            ha="center", fontsize=10.5, color=MUTED)

    plt.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {path}")


# ══════════════════════════════════════════════════════════════════════════════
# GRÁFICO 4 — Métricas reales del enrutador (datos que SÍ tenemos)
# ══════════════════════════════════════════════════════════════════════════════
def chart_routing_metrics(path: str):
    grupos = ["Dominio", "Especialista", "Tier en rango"]
    entrenamiento = [100, 100, 100]
    validacion = [96, 96, 96]

    x = np.arange(len(grupos))
    w = 0.36
    fig, ax = plt.subplots(figsize=(10, 6))
    b1 = ax.bar(x - w/2, entrenamiento, w, label="Entrenamiento (51 casos)",
                color=ACCENT, zorder=3)
    b2 = ax.bar(x + w/2, validacion, w, label="Validación (24 casos nuevos)",
                color=ACCENT2, zorder=3)

    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 1,
                    f"{int(b.get_height())}%", ha="center", va="bottom",
                    fontsize=12, fontweight="bold", color=TEXT)

    ax.set_ylim(0, 112)
    ax.set_ylabel("Precisión (%)", fontsize=13)
    ax.set_title("Precisión del enrutador de Andromeda",
                 fontsize=18, fontweight="bold", pad=16)
    ax.set_xticks(x); ax.set_xticklabels(grupos, fontsize=12)
    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(GRID)
    leg = ax.legend(frameon=False, fontsize=11, loc="lower center", ncol=2,
                    bbox_to_anchor=(0.5, -0.22))
    for t in leg.get_texts():
        t.set_color(TEXT)
    ax.text(0.5, -0.30,
            "Validado sobre casos nunca vistos para evitar sobreajuste · "
            "131 tests automatizados en verde",
            transform=ax.transAxes, ha="center", fontsize=10, color=MUTED)

    plt.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ {path}")


if __name__ == "__main__":
    import sys
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    chart_feature_matrix(f"{outdir}/andromeda_vs_comparativa.png")
    chart_cost(f"{outdir}/andromeda_coste_anual.png")
    chart_orchestration(f"{outdir}/andromeda_orquestacion.png")
    chart_routing_metrics(f"{outdir}/andromeda_metricas_router.png")
    print("Listo.")
