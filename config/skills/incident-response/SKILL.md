---
name: Incident Response
description: Diagnosticar una caída de servicio, un error en producción o un comportamiento inesperado del sistema en tiempo real.
triggers: caído caída incidente producción 500 error outage down alerta urgente
specialists: [it-ops, verifier]
---
Ante un incidente, en este orden:

1. **Contener**: ¿hay que revertir, apagar algo, o bajar tráfico ya? No investigues la causa raíz antes de contener el daño.
2. **Diagnosticar**: qué cambió justo antes (deploy, config, tráfico, dependencia externa). Pide logs y métricas concretas, no adivines.
3. **Comunicar**: un resumen de una frase del estado actual, apto para compartir con quien pregunte "¿qué está pasando?".
4. **Postmortem**: una vez resuelto, causa raíz, por qué no se detectó antes, y una acción concreta para que no vuelva a pasar.

Sé directo sobre la severidad. No minimices un incidente en curso ni lo dramatices si es menor.
