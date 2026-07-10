# Post de LinkedIn — Andromeda Orquesta

> Enfoque: contar el aprendizaje técnico y la decisión de diseño, no vender un
> producto. En LinkedIn funciona mucho mejor "construí esto y aprendí X" que
> "mirad mi producto". Adjunta el GIF de la fusión o el diagrama del pipeline.

---

## Versión larga (post principal)

Llevo meses construyendo Andromeda: una plataforma de orquestación de IA que
corre 100% en local. Esta semana terminé la parte de la que más he aprendido,
y quería compartir la decisión de diseño detrás.

El problema: los modelos grandes (70B, 400B+) dan mejores respuestas, pero no
caben en una GPU de consumo. Los pequeños (3B-7B) caben pero se quedan cortos
en tareas difíciles. La pregunta que me hice fue: ¿y si en vez de un modelo
gigante uso el módulo del tamaño justo para cada tarea?

Eso es Andromeda Orquesta. Para cada prompt, un orquestador decide:

→ El DOMINIO (código, razonamiento, redacción, datos, charla)
→ La COMPLEJIDAD (un score de 0 a 1)
→ El TIER DE POTENCIA (1-4), combinando ambos

Lo interesante es que el tamaño óptimo no depende solo de cuán largo es el
prompt, sino del tipo de tarea. "Demuestra que √2 es irracional" es corto pero
exige un modelo capaz. Una charla larga no. El orquestador usa el modelo más
pequeño que basta, y solo escala cuando la tarea lo pide. Si la respuesta sale
floja, reintenta una vez en un modelo mayor.

Lo que más me ha enseñado este proyecto no es el código del enrutador, sino
medirlo. Monté un banco de pruebas con casos etiquetados y un conjunto de
validación separado. Pasé de un 75% de acierto en las decisiones a un 100% en
entrenamiento y 92-100% en validación — afinando con datos, no a ojo. Y lo dejé
con tests de regresión para que no se degrade.

¿Iguala esto a un modelo de 600B? No, y sería deshonesto decir que sí. Pero en
muchas tareas concretas se acerca mucho gastando una fracción de la memoria. Y
sobre todo: me ha enseñado a pensar como un ingeniero de sistemas de ML —
medir, validar, proteger la calidad.

Es open source. Enlace en los comentarios. Cualquier feedback es bienvenido,
sobre todo crítico.

#MachineLearning #LLM #MLOps #OpenSource #IA

---

## Versión corta (alternativa)

¿Y si en vez de un modelo de IA gigante usaras el módulo del tamaño justo para
cada tarea?

Eso es lo que construí esta semana en Andromeda (open source, 100% local): un
orquestador que lee cada prompt, detecta su dominio y complejidad, y elige
automáticamente la potencia mínima necesaria — escalando solo cuando hace falta.

Lo medí con un banco de pruebas: 100% de acierto en las decisiones de
enrutamiento, validado con casos nuevos. No iguala a un modelo de 600B, pero se
acerca en tareas concretas gastando una fracción de la memoria.

Lo que más me llevo: aprender a medir y validar un sistema de ML, no solo
construirlo. Enlace en comentarios.

#MachineLearning #LLM #MLOps #OpenSource

---

## Comentario para añadir (con el enlace)

GitHub: [tu-enlace-aquí]
Está todo documentado, incluido cómo funciona el orquestador y el banco de
pruebas. Si lo pruebas en tu máquina, me encantaría saber qué tal.
