---
name: Debugging
description: Diagnosticar por qué un programa falla, lanza una excepción, da un resultado incorrecto o se comporta de forma inesperada.
triggers: error excepción bug falla traceback stacktrace TypeError NullPointer crash falla
specialists: [software-engineering]
---
Depura de forma sistemática, no a base de suposiciones:

1. **Reproduce**: ¿cuál es el input mínimo que provoca el fallo? Si no se puede reproducir, no se puede arreglar.
2. **Lee el error de verdad**: el stack trace suele decir la línea exacta. Empieza por abajo (la causa) y sube.
3. **Aísla**: divide el problema por la mitad. ¿Falla antes o después de este punto? Repite hasta acorralarlo.
4. **Formula una hipótesis concreta** y una forma de comprobarla. "Creo que X es None aquí porque Y" es útil. "Debe de ser algo del caché" no lo es.
5. **Arregla la causa, no el síntoma**. Un try/except que silencia el error no es un arreglo.

Si te falta información (logs, versiones, el input real), pídela en vez de adivinar.
