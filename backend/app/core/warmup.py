"""
warmup.py — Sistema de precarga de modelos (keep_warm).

Los modelos marcados como keep_warm=true en specialists.yaml
se precalientan al arrancar el sistema enviando un prompt vacío.

Esto elimina la latencia de carga del modelo (~3-8 segundos)
en la primera petición real del usuario.

Diseño:
  - Se ejecuta en background al arrancar el servidor
  - No bloquea el arranque — si falla, el sistema sigue funcionando
  - Reintenta cada 30s si Ollama no está disponible todavía
  - Log claro de qué modelos están calientes y cuáles no
"""

import asyncio
import logging
import time

import httpx

logger = logging.getLogger("andromeda.warmup")


async def warmup_models(
    registry,
    ollama_url: str,
    hardware_tier: int = 1,
    vram_free_gb: float = 999.0,
    max_retries: int = 5,
) -> dict[str, bool]:
    """
    Precalienta los modelos marcados como keep_warm.

    Proceso por cada modelo:
      1. Resolver qué model_name usar según el hardware
      2. Enviar un prompt mínimo a Ollama para cargar el modelo en VRAM
      3. Registrar el resultado (éxito/fallo)

    Args:
        registry:      SpecialistRegistry con la configuración
        ollama_url:    URL base de Ollama
        hardware_tier: Tier de hardware detectado
        vram_free_gb:  VRAM libre disponible
        max_retries:   Reintentos si Ollama no está listo

    Returns:
        Dict {specialist_id: True/False} — True = calentado correctamente
    """
    warm_ids = registry.get_warm_specialists()

    if not warm_ids:
        logger.info("Ningún modelo marcado como keep_warm — precarga omitida")
        return {}

    logger.info(f"Iniciando precarga de {len(warm_ids)} modelos: {warm_ids}")

    # Esperar a que Ollama esté disponible (puede tardar si acaba de arrancar)
    ollama_ready = False
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                r = await client.get(f"{ollama_url}/api/tags", timeout=5.0)
                if r.status_code == 200:
                    ollama_ready = True
                    break
        except Exception:
            pass
        if attempt < max_retries - 1:
            logger.info(f"Ollama no listo, reintentando en 10s... ({attempt+1}/{max_retries})")
            await asyncio.sleep(10)

    if not ollama_ready:
        logger.warning("Ollama no disponible — precarga cancelada. Los modelos se cargarán en el primer uso.")
        return {sid: False for sid in warm_ids}

    # Calentar cada modelo en paralelo
    results = {}
    tasks = []

    for specialist_id in warm_ids:
        if specialist_id == "orchestrator":
            model_name = registry.orchestrator_model
        else:
            try:
                model_name, level = registry.resolve_model_for_tier(
                    specialist_id, hardware_tier, vram_free_gb
                )
            except Exception:
                continue

        if not model_name or model_name == "PENDIENTE_CONFIGURAR":
            logger.debug(f"Precarga omitida para '{specialist_id}' — modelo no configurado")
            results[specialist_id] = False
            continue

        tasks.append(_warm_model(specialist_id, model_name, ollama_url))

    # Lanzar todos en paralelo
    if tasks:
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        for specialist_id, result in zip(warm_ids, task_results):
            if isinstance(result, Exception):
                results[specialist_id] = False
                logger.warning(f"Precarga '{specialist_id}' falló: {result}")
            else:
                results[specialist_id] = result

    warm_ok  = [k for k, v in results.items() if v]
    warm_fail = [k for k, v in results.items() if not v]

    if warm_ok:
        logger.info(f"✓ Modelos precargados: {warm_ok}")
    if warm_fail:
        logger.warning(f"✗ Precarga fallida: {warm_fail}")

    return results


async def _warm_model(specialist_id: str, model_name: str, ollama_url: str) -> bool:
    """
    Envía un prompt mínimo para cargar el modelo en VRAM.
    Ollama mantiene el modelo en memoria después de esta llamada.
    """
    t_start = time.perf_counter()
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": " ",          # Prompt mínimo
                    "stream": False,
                    "options": {"num_predict": 1},  # Generar solo 1 token
                },
                timeout=60.0,   # Los modelos grandes tardan en cargar
            )
            resp.raise_for_status()

        elapsed = (time.perf_counter() - t_start) * 1000
        logger.info(
            f"✓ Modelo '{model_name}' ({specialist_id}) precargado en {elapsed:.0f}ms"
        )
        return True

    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.warning(
                f"Modelo '{model_name}' no encontrado en Ollama. "
                f"Descárgalo con: ollama pull {model_name}"
            )
        else:
            logger.error(f"Error precargando '{model_name}': HTTP {exc.response.status_code}")
        return False

    except Exception as exc:
        logger.error(f"Error precargando '{model_name}': {exc}")
        return False


async def check_warm_status(registry, ollama_url: str) -> dict[str, dict]:
    """
    Comprueba qué modelos están actualmente en memoria de Ollama.

    Ollama expone en /api/ps los modelos actualmente cargados.
    Útil para la UI de Modelos — mostrar qué está "caliente".

    Returns:
        Dict {model_name: {size_mb, loaded_duration_s, ...}}
    """
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(f"{ollama_url}/api/ps", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                loaded = {}
                for model in data.get("models", []):
                    name = model.get("name", "")
                    loaded[name] = {
                        "size_mb":    round(model.get("size", 0) / 1024 / 1024, 0),
                        "expires_at": model.get("expires_at", ""),
                        "hot":        True,
                    }
                return loaded
    except Exception:
        pass
    return {}
