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

---

# Post de LinkedIn — Andromeda 1.1

> Mismo enfoque: el aprendizaje, no el producto. El hilo de este post es cómo
> encontré los fallos: con telemetría de uso real, no con suposiciones. Es lo
> que más encaja con un perfil de MLOps. Imagen: `docs/media/chart-memory-speed-dark.png`.
> Enlace al repo en el primer comentario.

## Versión larga

Acabo de publicar Andromeda 1.1, mi app de IA que corre 100 % en local.

La novedad visible es un diseño nuevo inspirado en macOS y una memoria que
funciona como la de Claude: organizada por temas, y editable describiendo el
cambio con tus palabras.

Pero lo que más me ha enseñado esta versión no se ve.

Durante semanas usé la app a diario con un panel de diagnóstico que registraba
cada paso de cada mensaje: qué contexto se construía, qué herramientas se
elegían, cuánto tardaba cada fase. Luego leía esos registros como quien lee los
logs de producción.

Algunas cosas que encontré así:

→ En macOS, cada mensaje ejecutaba un comando del sistema que tarda entre 0,3 y
1 segundo antes de empezar a generar. Para devolver un número que además era
falso.

→ Las búsquedas web perdían entre 2 y 4 segundos probando buscadores que
fallaban siempre. Ahora recuerda cuál funciona.

→ Los votos 👍/👎 llevaban semanas sin asociarse a su respuesta por un problema
de reactividad en la interfaz. El dataset para afinar mi propio modelo estaba
vacío y nada lo indicaba.

→ La memoria semántica tenía un umbral tan alto que casi nunca encontraba nada.

Ninguno de estos fallos aparecía en los tests. Todos aparecían en los registros.

La lección para mí: los tests te dicen si el código hace lo que pensabas. La
telemetría te dice si lo que pensabas era correcto.

Números de la 1.1: 1.257 tests en Linux, macOS y Windows, preparar cada mensaje
pasa de 28 ms a 2 ms, la búsqueda en la memoria es unas 8 veces más rápida (con
5.000 recuerdos, de 1,5 s a 0,17 s, con resultados idénticos comprobados por test)
y la memoria por significado viene activada de base.

Es open source (MIT). Enlace en el primer comentario.

#MLOps #LocalAI #OpenSource #Ollama #Python

## Versión corta

Publicada Andromeda 1.1, mi app de IA 100 % local.

Diseño nuevo inspirado en macOS, memoria organizada como la de Claude y búsqueda
por significado activada de base.

Lo que más aprendí: los peores fallos no los encontraron los tests, sino los
registros de uso real. Un comando que añadía hasta 1 s a cada mensaje en Mac,
búsquedas que perdían 3 s probando buscadores rotos, votos que no se guardaban.

Los tests dicen si el código hace lo que pensabas. La telemetría, si lo que
pensabas era correcto.

Open source, enlace en comentarios. #MLOps #LocalAI #OpenSource

## Primer comentario

Repositorio: https://github.com/PauAlonsoRacero/andromeda-lite
Descarga para macOS y Windows en la release 1.1.0. Necesita Ollama.
