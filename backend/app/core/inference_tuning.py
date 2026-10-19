"""
inference_tuning.py — Parámetros de inferencia ajustados al hardware.

Andromeda solo enviaba a Ollama `temperature` y `num_predict`, dejando el resto
en los valores por defecto. Esos valores son conservadores a propósito, porque
Ollama no sabe en qué máquina corre. Andromeda sí: ya detecta CPU, RAM, VRAM y
tipo de aceleración, así que puede pedir una configuración mejor.

Los tres que más impactan:

  • num_ctx    — Tamaño de la ventana de contexto. Ollama usa 4096 por defecto.
                 Subirlo permite conversaciones más largas sin compactar, pero
                 consume memoria proporcionalmente, así que se escala con la
                 VRAM/RAM disponible.

  • num_gpu    — Cuántas capas del modelo van a la GPU. Ollama lo estima solo,
                 pero cuando acierta a la baja el modelo corre parcialmente en
                 CPU y la generación se desploma. Con VRAM de sobra conviene
                 forzar que vaya todo a la GPU.

  • num_thread — Hilos de CPU. Por defecto Ollama usa todos los núcleos, lo que
                 en portátiles satura el equipo y acaba siendo MÁS lento por
                 throttling térmico. Se deja un margen.

Todo es ajustable con variables de entorno para quien quiera afinarlo a mano.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("andromeda.tuning")

# Ventanas de contexto por franja de memoria. Un contexto grande no es gratis:
# la caché de atención crece con él y compite con los pesos del modelo.
_CTX_POR_MEMORIA = (
    (24, 16384),    # 24 GB+ de VRAM: contexto amplio sin apretar
    (12, 8192),     # 12-24 GB
    (8, 8192),      # 8-12 GB
    (6, 4096),      # 6-8 GB
    (0, 4096),      # por debajo: el valor por defecto de Ollama
)


def _env_int(nombre: str) -> int | None:
    valor = os.environ.get(nombre)
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        logger.warning(f"{nombre} no es un número entero: {valor!r}")
        return None


def context_window(memoria_gb: float) -> int:
    """Ventana de contexto adecuada para la memoria disponible."""
    forzado = _env_int("ANDROMEDA_NUM_CTX")
    if forzado:
        return max(512, min(forzado, 131072))
    for minimo, ctx in _CTX_POR_MEMORIA:
        if memoria_gb >= minimo:
            return ctx
    return 4096


def cpu_threads(nucleos: int) -> int | None:
    """Hilos de CPU a usar, o None para dejar que decida Ollama.

    Usar todos los núcleos parece lo óptimo pero en portátiles provoca
    throttling térmico y acaba generando MENOS tokens por segundo. Se reserva
    un núcleo a partir de 8, para que el sistema (y la propia interfaz de
    Andromeda) sigan respondiendo.
    """
    forzado = _env_int("ANDROMEDA_NUM_THREAD")
    if forzado:
        return max(1, forzado)
    if not nucleos or nucleos < 4:
        return None                      # equipos modestos: que decida Ollama
    return max(4, nucleos - 1)


def gpu_layers(vram_gb: float, aceleracion: str) -> int | None:
    """Capas a descargar en GPU, o None para que Ollama lo estime.

    Ollama estima cuántas capas caben, pero cuando se queda corto el modelo
    corre parcialmente en CPU y la velocidad cae en picado. Con VRAM holgada se
    le pide explícitamente que use la GPU para todo (999 = todas las capas).

    En Apple Silicon no se toca: la memoria es unificada y el reparto lo hace
    Metal mucho mejor que una heurística nuestra.
    """
    forzado = _env_int("ANDROMEDA_NUM_GPU")
    if forzado is not None:
        return forzado
    acel = (aceleracion or "").lower()
    if "metal" in acel or "apple" in acel:
        return None                      # memoria unificada: no forzar nada
    if "cuda" in acel or "rocm" in acel or "nvidia" in acel:
        if vram_gb >= 8:
            return 999                   # todas las capas a la GPU
    return None


def build_options(
    base: dict | None = None,
    *,
    vram_gb: float = 0.0,
    ram_gb: float = 0.0,
    cpu_cores: int = 0,
    acceleration: str = "",
) -> dict:
    """Combina las opciones de la petición con las ajustadas al hardware.

    Lo que venga en `base` (temperatura, num_predict…) manda siempre: son
    decisiones explícitas de quien llama.
    """
    opciones = dict(base or {})

    # Con GPU manda la VRAM; sin ella, la RAM del sistema.
    memoria = vram_gb if vram_gb > 0 else ram_gb

    opciones.setdefault("num_ctx", context_window(memoria))

    hilos = cpu_threads(cpu_cores)
    if hilos is not None:
        opciones.setdefault("num_thread", hilos)

    capas = gpu_layers(vram_gb, acceleration)
    if capas is not None:
        opciones.setdefault("num_gpu", capas)

    lote = batch_size(vram_gb, acceleration)
    if lote is not None:
        opciones.setdefault("num_batch", lote)

    # La respuesta no puede ser más larga que el contexto: hay que dejar sitio
    # al prompt. Así el límite de 8192 no desborda equipos con contexto pequeño.
    ctx = opciones.get("num_ctx")
    if ctx and opciones.get("num_predict"):
        opciones["num_predict"] = min(int(opciones["num_predict"]), max(1024, int(ctx * 0.6)))

    return opciones


def options_from_hardware(base: dict | None, hardware) -> dict:
    """Igual que build_options, tomando los datos del detector de hardware."""
    if hardware is None:
        return dict(base or {})
    return build_options(
        base,
        vram_gb=float(getattr(hardware, "total_vram_gb", 0) or 0),
        ram_gb=float(getattr(hardware, "ram_total_gb", 0) or 0),
        cpu_cores=int(getattr(hardware, "cpu_cores", 0) or 0),
        acceleration=str(getattr(hardware, "acceleration", "") or ""),
    )

# Tamaño de lote en la fase de prefill (procesar el prompt). Ollama usa 512 por
# defecto; subirlo acelera notablemente el procesado de prompts largos porque
# aprovecha mejor el paralelismo de la GPU, a costa de algo más de memoria
# durante esa fase. Solo tiene sentido con VRAM holgada.
_BATCH_POR_VRAM = (
    (16, 2048),
    (10, 1024),
    (0, 512),      # el valor por defecto de Ollama
)


def batch_size(vram_gb: float, aceleracion: str) -> int | None:
    """Tamaño de lote para el prefill, o None para dejar el de Ollama.

    Afecta a cuánto tarda el modelo en "leer" el prompt antes de empezar a
    responder, que es justo la parte que el usuario percibe como espera inicial.
    """
    forzado = _env_int("ANDROMEDA_NUM_BATCH")
    if forzado:
        return max(32, forzado)
    acel = (aceleracion or "").lower()
    if not any(x in acel for x in ("cuda", "rocm", "nvidia", "metal", "apple")):
        return None                      # sin GPU, lotes grandes no ayudan
    for minimo, lote in _BATCH_POR_VRAM:
        if vram_gb >= minimo:
            return lote if lote != 512 else None
    return None


def recommended_server_env(vram_gb: float, aceleracion: str) -> dict[str, str]:
    """Variables que convienen en el SERVIDOR de Ollama, no en la petición.

    Andromeda no puede cambiarlas en un Ollama ya arrancado (son del proceso
    servidor), pero sí puede detectar que faltan y decírselo al usuario:

      • OLLAMA_FLASH_ATTENTION=1  — atención optimizada; el propio equipo de
        Ollama la recomienda para maximizar el rendimiento en GPU.
      • OLLAMA_KV_CACHE_TYPE=q8_0 — cuantiza la caché de atención. Junto con
        Flash Attention permite aproximadamente el doble de contexto antes de
        quedarse sin memoria.

    Se recomienda q8_0 y no q4_0: la caché es más sensible a la cuantización
    que los pesos, y a 4 bits la calidad se resiente en contextos largos.
    """
    acel = (aceleracion or "").lower()
    if not any(x in acel for x in ("cuda", "rocm", "nvidia")):
        return {}                        # Flash Attention es de CUDA/ROCm
    recomendado = {"OLLAMA_FLASH_ATTENTION": "1"}
    if vram_gb < 16:
        # Con VRAM ajustada, cuantizar la caché es lo que permite contextos
        # largos sin quedarse sin memoria.
        recomendado["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
    return recomendado
