---
name: Refactoring
description: Reestructurar o limpiar código existente sin cambiar su comportamiento, reducir duplicación y mejorar la legibilidad.
triggers: refactor refactorizar limpiar duplicación legacy reestructurar deuda técnica
specialists: [software-engineering]
---
Al refactorizar:

- **Regla de oro**: el comportamiento observable no cambia. Si cambia, no es un refactor, es una reescritura, y debe decirse.
- Sin tests que cubran el código, el primer paso es escribirlos. Refactorizar a ciegas es romper cosas en diferido.
- Un cambio a la vez, verificable. No mezcles renombrar, extraer función y cambiar lógica en el mismo paso.
- Extrae una función cuando puedas darle un nombre claro. Si no sabes cómo llamarla, quizá no es una unidad real.
- Duplicación: tres repeticiones son señal para abstraer. Dos, muchas veces no.
- La abstracción prematura cuesta más que la duplicación. No generalices para casos que aún no existen.

Muestra el antes y el después, y di explícitamente qué garantiza que el comportamiento no cambió.
