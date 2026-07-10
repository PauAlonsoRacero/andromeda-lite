"""
stats.py — Significancia estadística para experimentos A/B.

Decidir un "ganador" por tasa de éxito sin más es un error clásico: con pocas
muestras, el ruido manda. Aquí aplicamos un test z de dos proporciones para saber
si la diferencia entre dos variantes es ESTADÍSTICAMENTE significativa, además de
un guardarraíl de tamaño mínimo de muestra antes de declarar nada.

Sin dependencias externas: implementamos la CDF normal con una aproximación de
error function (erf), suficiente para un p-valor fiable.
"""
from __future__ import annotations

import math

# Nº mínimo de peticiones por variante antes de tomar en serio un resultado.
MIN_SAMPLE = 30
# Umbral de significancia (p < 0.05 → 95% de confianza).
ALPHA = 0.05


def _normal_cdf(z: float) -> float:
    """Función de distribución acumulada de la normal estándar."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_proportion_z_test(succ_a: int, n_a: int, succ_b: int, n_b: int) -> dict:
    """Test z de dos proporciones (tasas de éxito de A vs B).

    Devuelve el estadístico z, el p-valor (bilateral) y si es significativo.
    """
    if n_a == 0 or n_b == 0:
        return {"z": 0.0, "p_value": 1.0, "significant": False}

    p_a = succ_a / n_a
    p_b = succ_b / n_b
    p_pool = (succ_a + succ_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        # Sin varianza (p.ej. ambas 100% o 0%): no hay diferencia detectable.
        return {"z": 0.0, "p_value": 1.0, "significant": False}

    z = (p_a - p_b) / se
    p_value = 2 * (1 - _normal_cdf(abs(z)))   # bilateral
    return {
        "z": round(z, 3),
        "p_value": round(p_value, 4),
        "significant": p_value < ALPHA,
    }


def assess(variants: dict) -> dict:
    """Dado {variant: {requests, successes, ...}}, decide ganador con rigor.

    Compara la mejor variante contra la segunda mejor por tasa de éxito y aplica
    el test z. Solo declara ganador si hay muestra suficiente Y significancia.
    """
    ranked = sorted(
        variants.items(),
        key=lambda kv: (kv[1]["successes"] / kv[1]["requests"]) if kv[1]["requests"] else -1,
        reverse=True,
    )
    enough = all(v["requests"] >= MIN_SAMPLE for _, v in ranked[:2]) if len(ranked) >= 2 else False

    result = {
        "winner": None,
        "confident": False,
        "enough_sample": enough,
        "min_sample": MIN_SAMPLE,
        "test": None,
    }
    if len(ranked) < 2:
        return result

    (name_a, a), (_, b) = ranked[0], ranked[1]
    test = two_proportion_z_test(a["successes"], a["requests"],
                                 b["successes"], b["requests"])
    result["test"] = test
    result["leader"] = name_a
    # Ganador con confianza solo si hay muestra suficiente y el test es significativo.
    if enough and test["significant"]:
        result["winner"] = name_a
        result["confident"] = True
    return result


# Muestra mínima de VOTOS de calidad (👍/👎) antes de declarar un ganador de calidad.
MIN_QUALITY_SAMPLE = 20


def assess_quality(variants: dict) -> dict:
    """Igual que assess() pero sobre la CALIDAD percibida (satisfacción 👍/👎).

    La tasa de éxito dice si la inferencia terminó; la satisfacción dice si la
    respuesta fue buena. Este es a menudo el veredicto que de verdad importa.
    """
    rated = {n: v for n, v in variants.items() if v.get("ratings", 0) > 0}
    result = {
        "quality_winner": None,
        "quality_confident": False,
        "quality_enough_sample": False,
        "quality_min_sample": MIN_QUALITY_SAMPLE,
        "quality_test": None,
    }
    if len(rated) < 2:
        return result

    ranked = sorted(
        rated.items(),
        key=lambda kv: kv[1].get("positive", 0) / kv[1]["ratings"],
        reverse=True,
    )
    (name_a, a), (_, b) = ranked[0], ranked[1]
    enough = all(v["ratings"] >= MIN_QUALITY_SAMPLE for _, v in ranked[:2])
    result["quality_enough_sample"] = enough
    result["quality_leader"] = name_a
    test = two_proportion_z_test(a.get("positive", 0), a["ratings"],
                                 b.get("positive", 0), b["ratings"])
    result["quality_test"] = test
    if enough and test["significant"]:
        result["quality_winner"] = name_a
        result["quality_confident"] = True
    return result
