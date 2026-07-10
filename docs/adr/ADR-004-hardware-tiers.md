# ADR-004: Definición de los 4 tiers de hardware de Andromeda

## Estado
Aceptado — Fase 0

## Contexto

Andromeda debe funcionar desde equipos con 8 GB de VRAM hasta servidores con 128+ GB. Sin un sistema de tiers definido, el sistema tendría que ser configurado manualmente por el usuario para cada hardware. Esto viola el principio central: **la adaptabilidad es una capacidad fundacional, no un feature secundario**.

Necesitamos umbrales de VRAM que:
1. Sean suficientemente granulares para capturar diferencias de comportamiento reales
2. Sean suficientemente simples para que el usuario entienda en qué tier está
3. Se alineen con los rangos de GPU más comunes en el mercado

## Decisión

Definimos **4 tiers** basados en VRAM disponible para inferencia:

| Tier | VRAM | GPU típica | max_parallel | Cuantización | Estrategias |
|------|------|-----------|-------------|-------------|-------------|
| T1   | 4–8 GB  | RTX 3060, M1 8GB | 1 | Q4_K_M | single, latency_first, fallback |
| T2   | 8–16 GB | RTX 3080, RTX 4070, M2 Pro | 2 | Q5_K_M | + iterative_refine, verifier_pass |
| T3   | 16–48 GB| RTX 3090, RTX 4090, M2 Max | 3 | Q8_0   | + confidence_weighted, quality_first |
| T4   | 48+ GB  | A100, H100, Mac Studio Ultra | 3 | fp16 | todas |

**Criterio de degradación** dentro de cada tier:
- VRAM libre < threshold * 1.5 → modo preventivo (reducir paralelo)
- VRAM libre < threshold → modo seguridad (single + generalist)

**CPU-only** (sin GPU):
- RAM >= 32 GB → T2 (modelos pequeños en CPU, lento pero funcional)
- RAM < 32 GB → T1

## Consecuencias

**Positivas:**
- El usuario siempre sabe en qué tier está (visible en el hardware panel)
- El Policy Engine deriva automáticamente el comportamiento sin configuración manual
- Los umbrales son conservadores — preferimos degradar antes que un OOM
- Apple Silicon funciona correctamente (memoria unificada tratada como VRAM)

**Negativas:**
- Los umbrales son aproximaciones — diferentes modelos consumen VRAM de forma diferente
- Una GPU con 8 GB puede ser T1 o T2 dependiendo de cuántos modelos están cargados
- El tier se detecta al arranque, no en tiempo real (Fase 1 añade detección dinámica)

## Alternativas consideradas

**2 tiers (ligero/potente)**: demasiado grueso. La diferencia entre 8 GB y 48 GB es enorme en términos de estrategias disponibles.

**6+ tiers**: demasiado granular. La complejidad del Policy Engine crece sin beneficio proporcional para el usuario.

**Sin tiers, configuración manual**: viola el principio de adaptabilidad fundacional. El usuario no debería tener que saber qué cuantización usar.
