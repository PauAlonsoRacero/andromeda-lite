---
name: Code Review
description: Revisar cambios de código en busca de bugs, problemas de seguridad, rendimiento y estilo antes de hacer merge o desplegar.
triggers: pull request PR merge revisar código commit diff cambios aprobar
specialists: [software-engineering, verifier]
---
Al revisar código, sigue esta estructura:

1. **Correctud**: ¿hace lo que dice que hace? Casos límite no cubiertos.
2. **Seguridad**: inyección, datos sin validar, secretos hardcodeados, path traversal.
3. **Rendimiento**: complejidad innecesaria, N+1, bloqueos síncronos en rutas async.
4. **Estilo y mantenibilidad**: nombres claros, funciones cortas, tests que faltan.

Para cada hallazgo indica: severidad (alta/media/baja), ubicación exacta, por qué es un problema, y una corrección concreta. No inventes problemas sin evidencia en el código mostrado. Si el código está bien, dilo claramente en vez de forzar comentarios.
