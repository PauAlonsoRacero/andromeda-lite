/**
 * promptCatalog.js — Prompts prefabricados.
 *
 * Los [corchetes] marcan lo que hay que rellenar. Están escritos en español; la
 * IA responde igualmente en el idioma de la interfaz.
 */
const P = (cat, title, body) => ({ cat, title, body })

export const PROMPT_CATEGORIES = [
  'Programación', 'Escritura', 'Estudio', 'Trabajo y carrera', 'Negocio', 'Marketing',
  'Productividad', 'Datos y análisis', 'Diseño y web', 'Finanzas personales',
  'Salud y deporte', 'Idiomas', 'Viajes', 'Creatividad', 'Vida diaria',
]

export const PROMPT_CATALOG = [
  // ── Programación ─────────────────────────────────────────────────────
  P('Programación', 'Revisar código', 'Revisa este código como un ingeniero senior. Señala errores, problemas de seguridad, rendimiento y legibilidad, ordenados por gravedad, y propón la versión corregida:\n\n[pega el código]'),
  P('Programación', 'Explicar código línea a línea', 'Explícame qué hace este código, paso a paso, como si fuera la primera vez que veo este lenguaje:\n\n[pega el código]'),
  P('Programación', 'Encontrar un bug', 'Este código debería [comportamiento esperado] pero hace [comportamiento real]. Encuentra la causa, explícala y dame el arreglo:\n\n[pega el código y el error]'),
  P('Programación', 'Escribir tests', 'Escribe tests unitarios completos con [pytest / Jest / JUnit] para este código. Cubre casos normales, límites y errores:\n\n[pega el código]'),
  P('Programación', 'Refactorizar', 'Refactoriza este código para que sea más limpio y mantenible sin cambiar su comportamiento. Explica cada cambio:\n\n[pega el código]'),
  P('Programación', 'Optimizar rendimiento', 'Este código es lento con [volumen de datos]. Identifica los cuellos de botella y reescríbelo para que sea más rápido, indicando la complejidad antes y después:\n\n[pega el código]'),
  P('Programación', 'Traducir entre lenguajes', 'Traduce este código de [lenguaje origen] a [lenguaje destino] de forma idiomática, no literal:\n\n[pega el código]'),
  P('Programación', 'Diseñar una API REST', 'Diseña una API REST para [descripción del sistema]: recursos, endpoints, métodos, códigos de estado, ejemplos de petición/respuesta y autenticación.'),
  P('Programación', 'Esquema de base de datos', 'Diseña el esquema de base de datos para [aplicación]. Incluye tablas, claves, relaciones, índices y el SQL de creación.'),
  P('Programación', 'Consulta SQL', 'Escribe una consulta SQL para [lo que necesitas obtener]. Tablas disponibles:\n\n[describe las tablas y columnas]'),
  P('Programación', 'Expresión regular', 'Escríbeme una expresión regular que [qué debe coincidir]. Explica cada parte y dame ejemplos que sí y que no coinciden.'),
  P('Programación', 'Script de automatización', 'Crea un script en [Python / Bash / PowerShell] que [tarea a automatizar]. Con manejo de errores y comentarios.'),
  P('Programación', 'Dockerizar un proyecto', 'Crea un Dockerfile y un docker-compose.yml para esta aplicación [tipo de app y dependencias], optimizados para producción.'),
  P('Programación', 'Pipeline de CI/CD', 'Crea un workflow de GitHub Actions que haga lint, tests y despliegue de un proyecto [tecnología] en [destino].'),
  P('Programación', 'Documentar código', 'Escribe la documentación de este código: docstrings, un README con instalación y uso, y ejemplos:\n\n[pega el código]'),
  P('Programación', 'Mensaje de commit', 'Escribe un mensaje de commit convencional (conventional commits) para estos cambios:\n\n[describe o pega el diff]'),
  P('Programación', 'Explicar un error', 'Explícame este error, por qué ocurre y cómo solucionarlo:\n\n[pega el error completo]'),
  P('Programación', 'Arquitectura de un sistema', 'Propón la arquitectura para [sistema] que soporte [usuarios / carga]. Componentes, tecnologías, diagrama en texto y compromisos.'),

  // ── Escritura ────────────────────────────────────────────────────────
  P('Escritura', 'Mejorar un texto', 'Mejora este texto: más claro, conciso y natural, sin cambiar el significado. Muestra la versión final y los cambios importantes:\n\n[pega el texto]'),
  P('Escritura', 'Corregir ortografía y gramática', 'Corrige la ortografía, gramática y puntuación de este texto. Devuelve el texto corregido y una lista de los errores:\n\n[pega el texto]'),
  P('Escritura', 'Resumir', 'Resume este texto en [5 puntos / un párrafo / 100 palabras], conservando las ideas clave:\n\n[pega el texto]'),
  P('Escritura', 'Cambiar el tono', 'Reescribe este texto con un tono [formal / cercano / persuasivo / neutro]:\n\n[pega el texto]'),
  P('Escritura', 'Email profesional', 'Escribe un email profesional a [destinatario] para [objetivo]. Tono [formal / cordial]. Breve y con un asunto claro.'),
  P('Escritura', 'Responder a un email', 'Ayúdame a responder a este email. Quiero [lo que quieres decir]:\n\n[pega el email]'),
  P('Escritura', 'Artículo de blog', 'Escribe un artículo de blog de unas [800] palabras sobre [tema] para [público]. Con título, introducción, secciones con subtítulos y conclusión.'),
  P('Escritura', 'Esquema de un documento', 'Crea el esquema detallado (índice con secciones y puntos clave) para un documento sobre [tema] dirigido a [público].'),
  P('Escritura', 'Carta formal', 'Redacta una carta formal a [destinatario] para [motivo], con el formato adecuado.'),
  P('Escritura', 'Discurso', 'Escribe un discurso de [duración] minutos para [ocasión], dirigido a [público], en tono [emotivo / inspirador / divertido].'),
  P('Escritura', 'Documento Word', 'Crea un documento Word detallado sobre [tema] con título, índice, secciones con subtítulos, tablas donde ayuden y conclusiones.'),

  // ── Estudio ──────────────────────────────────────────────────────────
  P('Estudio', 'Explicar un concepto', 'Explícame [concepto] de forma sencilla, con una analogía y un ejemplo práctico. Después, la explicación técnica.'),
  P('Estudio', 'Plan de estudio', 'Hazme un plan de estudio de [semanas] semanas para aprender [materia] desde nivel [inicial / intermedio], con [horas] horas a la semana, recursos y objetivos por semana.'),
  P('Estudio', 'Preguntas de examen', 'Genera [10] preguntas tipo examen sobre [tema], con las respuestas correctas y una breve explicación de cada una.'),
  P('Estudio', 'Test tipo test', 'Crea un test de [15] preguntas de opción múltiple sobre [tema], con 4 opciones cada una y la solución razonada al final.'),
  P('Estudio', 'Tarjetas de memoria', 'Crea [20] tarjetas de memoria (pregunta / respuesta) para repasar [tema].'),
  P('Estudio', 'Resumen para examen', 'Hazme un resumen para estudiar [tema]: conceptos clave, definiciones, fórmulas y lo que suele caer en examen.'),
  P('Estudio', 'Resolver paso a paso', 'Resuelve este problema paso a paso, explicando el razonamiento de cada paso:\n\n[pega el problema]'),
  P('Estudio', 'Comparar conceptos', 'Compara [concepto A] y [concepto B] en una tabla: definición, diferencias, similitudes, cuándo usar cada uno y ejemplos.'),
  P('Estudio', 'Mapa conceptual', 'Crea un mapa conceptual en texto (jerarquía con sangrías) de [tema], con las relaciones entre ideas.'),

  // ── Trabajo y carrera ────────────────────────────────────────────────
  P('Trabajo y carrera', 'Mejorar mi CV', 'Revisa mi CV para un puesto de [puesto]. Dime qué mejorar, reescribe los logros con impacto medible y adapta las palabras clave:\n\n[pega tu CV]'),
  P('Trabajo y carrera', 'Carta de presentación', 'Escribe una carta de presentación para el puesto de [puesto] en [empresa]. Mi experiencia relevante: [resumen].'),
  P('Trabajo y carrera', 'Preparar una entrevista', 'Prepárame para una entrevista de [puesto]: las 15 preguntas más probables (técnicas y de comportamiento) con respuestas modelo usando el método STAR.'),
  P('Trabajo y carrera', 'Simular una entrevista', 'Actúa como entrevistador para el puesto de [puesto]. Hazme una pregunta cada vez, espera mi respuesta y dame feedback antes de la siguiente.'),
  P('Trabajo y carrera', 'Negociar salario', 'Ayúdame a negociar el salario para [puesto] en [ciudad]. Rango de mercado aproximado, argumentos y qué decir exactamente.'),
  P('Trabajo y carrera', 'Perfil de LinkedIn', 'Escribe el titular y el extracto de mi perfil de LinkedIn. Soy [rol] con experiencia en [áreas] y busco [objetivo].'),
  P('Trabajo y carrera', 'Plan de carrera', 'Soy [situación actual] y quiero llegar a [objetivo profesional] en [plazo]. Hazme un plan con habilidades, certificaciones, proyectos e hitos.'),
  P('Trabajo y carrera', 'Acta de reunión', 'Convierte estas notas de reunión en un acta con decisiones, tareas (responsable y fecha) y temas pendientes:\n\n[pega las notas]'),

  // ── Negocio ──────────────────────────────────────────────────────────
  P('Negocio', 'Plan de negocio', 'Crea un plan de negocio para [idea]: problema, solución, mercado, competencia, modelo de ingresos, costes, plan de lanzamiento y riesgos.'),
  P('Negocio', 'Análisis DAFO', 'Haz un análisis DAFO de [empresa / proyecto] en una tabla, y extrae 3 acciones estratégicas.'),
  P('Negocio', 'Validar una idea', 'Evalúa de forma crítica esta idea de negocio: [idea]. Qué puede fallar, cómo validarla barato en 2 semanas y qué métricas mirar.'),
  P('Negocio', 'Análisis de competencia', 'Compara [mi producto] con [competidores] en una tabla: precio, funciones, público y puntos fuertes y débiles.'),
  P('Negocio', 'Pitch para inversores', 'Escribe un pitch de 2 minutos para [startup] dirigido a inversores: problema, solución, mercado, tracción y lo que pedimos.'),
  P('Negocio', 'Estructura de precios', 'Propón una estrategia de precios para [producto / servicio] con 3 niveles, qué incluye cada uno y por qué.'),
  P('Negocio', 'Propuesta comercial', 'Redacta una propuesta comercial para [cliente] ofreciendo [servicio], con alcance, plazos, precio y próximos pasos.'),

  // ── Marketing ────────────────────────────────────────────────────────
  P('Marketing', 'Posts para redes', 'Escribe [5] publicaciones para [Instagram / LinkedIn / X] sobre [tema], para [público]. Con gancho inicial y llamada a la acción.'),
  P('Marketing', 'Calendario de contenidos', 'Crea un calendario de contenidos de 4 semanas para [marca] en [redes], con tema, formato y objetivo de cada publicación.'),
  P('Marketing', 'Eslóganes', 'Propón 15 eslóganes para [producto / marca] que transmitan [valores]. Variados: cortos, emotivos y directos.'),
  P('Marketing', 'Texto para landing page', 'Escribe el texto de una landing page para [producto]: titular, subtítulo, beneficios, prueba social, preguntas frecuentes y llamada a la acción.'),
  P('Marketing', 'Descripción de producto', 'Escribe una descripción de producto persuasiva para [producto], destacando beneficios, no solo características.'),
  P('Marketing', 'Palabras clave SEO', 'Dame una lista de palabras clave SEO para [tema / negocio], agrupadas por intención de búsqueda, con ideas de artículo para cada grupo.'),
  P('Marketing', 'Guion de vídeo', 'Escribe el guion de un vídeo de [duración] para [plataforma] sobre [tema], con gancho en los 3 primeros segundos.'),

  // ── Productividad ────────────────────────────────────────────────────
  P('Productividad', 'Organizar mi semana', 'Ayúdame a organizar mi semana. Tareas: [lista]. Horario disponible: [horario]. Prioriza y distribúyelas por días.'),
  P('Productividad', 'Priorizar tareas', 'Ordena estas tareas con la matriz de Eisenhower y dime por dónde empezar:\n\n[lista de tareas]'),
  P('Productividad', 'Dividir un proyecto', 'Divide este proyecto en tareas concretas con estimación de tiempo y dependencias: [proyecto].'),
  P('Productividad', 'Rutina diaria', 'Diséñame una rutina diaria para [objetivo], teniendo en cuenta que [horarios / restricciones].'),
  P('Productividad', 'Checklist', 'Crea una checklist completa para [tarea o evento].'),
  P('Productividad', 'Tomar una decisión', 'Tengo que decidir entre [opción A] y [opción B]. Mi contexto: [contexto]. Hazme una tabla de pros y contras y dame tu recomendación razonada.'),

  // ── Datos y análisis ─────────────────────────────────────────────────
  P('Datos y análisis', 'Analizar datos', 'Analiza estos datos: tendencias, valores atípicos y conclusiones principales, con una tabla resumen:\n\n[pega los datos]'),
  P('Datos y análisis', 'Fórmula de Excel', 'Escríbeme una fórmula de Excel que [lo que debe calcular]. Mis columnas son: [describe las columnas].'),
  P('Datos y análisis', 'Hoja de cálculo', 'Crea una hoja de Excel para [propósito] con las columnas, fórmulas y formato necesarios.'),
  P('Datos y análisis', 'Gráfico', 'Hazme un gráfico de [tipo] con estos datos y explica qué muestra:\n\n[pega los datos]'),
  P('Datos y análisis', 'Análisis con pandas', 'Escribe código Python con pandas para [análisis] sobre un CSV con estas columnas: [columnas].'),
  P('Datos y análisis', 'Interpretar estadística', 'Explícame qué significan estos resultados estadísticos y qué conclusiones puedo sacar:\n\n[pega los resultados]'),

  // ── Diseño y web ─────────────────────────────────────────────────────
  P('Diseño y web', 'Página web completa', 'Crea una página web completa en un solo archivo HTML sobre [tema]: diseño moderno y responsive, menú de navegación, secciones de [lista], animaciones suaves y paleta [colores].'),
  P('Diseño y web', 'Landing page', 'Crea una landing page en HTML y CSS para [producto], con hero, beneficios, testimonios, precios y formulario de contacto. Responsive.'),
  P('Diseño y web', 'Portfolio personal', 'Crea un portfolio web personal para un [profesión] con sobre mí, proyectos, habilidades y contacto. Diseño elegante y oscuro.'),
  P('Diseño y web', 'Componente de interfaz', 'Crea un componente [botón / tarjeta / modal / tabla] en HTML y CSS, accesible y con estados hover y focus.'),
  P('Diseño y web', 'Paleta de colores', 'Propón 3 paletas de colores para [marca / proyecto] que transmitan [sensación], con códigos hexadecimales y dónde usar cada color.'),
  P('Diseño y web', 'Revisar un diseño', 'Revisa este diseño o captura: jerarquía visual, legibilidad, accesibilidad y qué mejorarías. [adjunta la imagen]'),

  // ── Finanzas personales ──────────────────────────────────────────────
  P('Finanzas personales', 'Presupuesto mensual', 'Ayúdame a hacer un presupuesto mensual. Ingresos: [cantidad]. Gastos fijos: [lista]. Objetivo de ahorro: [cantidad].'),
  P('Finanzas personales', 'Plan de ahorro', 'Quiero ahorrar [cantidad] en [plazo]. Mis ingresos y gastos son [datos]. Hazme un plan realista.'),
  P('Finanzas personales', 'Entender un producto financiero', 'Explícame qué es [fondo indexado / ETF / hipoteca variable…], cómo funciona, riesgos y costes, sin jerga.'),
  P('Finanzas personales', 'Comparar opciones', 'Compara en una tabla [opción A] y [opción B] para [objetivo financiero], con costes, riesgos y horizonte. Recuerda que es información, no asesoramiento.'),
  P('Finanzas personales', 'Coste real de una compra', 'Calcula el coste total real de [compra] incluyendo [seguro, mantenimiento, impuestos…] y cuánto debería ganar al mes para permitírmelo.'),

  // ── Salud y deporte ──────────────────────────────────────────────────
  P('Salud y deporte', 'Rutina de entrenamiento', 'Crea una rutina de entrenamiento de [días] días por semana para [objetivo], nivel [principiante / intermedio], con ejercicios, series y descansos.'),
  P('Salud y deporte', 'Plan de comidas', 'Hazme un menú semanal equilibrado para [objetivo], [número] comidas al día, con lista de la compra. Preferencias: [preferencias].'),
  P('Salud y deporte', 'Recetas con lo que tengo', 'Tengo [ingredientes]. Dame 3 recetas sencillas que pueda hacer con eso.'),
  P('Salud y deporte', 'Mejorar el sueño', 'Dame un plan práctico para mejorar mi sueño. Ahora mismo [describe tus hábitos].'),

  // ── Idiomas ──────────────────────────────────────────────────────────
  P('Idiomas', 'Traducir con matices', 'Traduce este texto al [idioma] manteniendo el tono y las expresiones naturales, no literal:\n\n[pega el texto]'),
  P('Idiomas', 'Practicar conversación', 'Practiquemos [idioma] a nivel [nivel]. Habla solo en [idioma], corrige mis errores al final de cada respuesta y hazme preguntas sobre [tema].'),
  P('Idiomas', 'Explicar gramática', 'Explícame [punto gramatical] en [idioma] con reglas, excepciones y 10 ejemplos.'),
  P('Idiomas', 'Vocabulario temático', 'Dame las 30 palabras y expresiones más útiles en [idioma] sobre [tema], con traducción y un ejemplo cada una.'),

  // ── Viajes ───────────────────────────────────────────────────────────
  P('Viajes', 'Itinerario de viaje', 'Planifica un viaje de [días] días a [destino] en [época], con presupuesto [presupuesto]. Itinerario por días, transporte, comida y consejos.'),
  P('Viajes', 'Lista de equipaje', 'Hazme una lista de equipaje para [días] días en [destino] en [época], para [tipo de viaje].'),
  P('Viajes', 'Presupuesto de viaje', 'Estima el presupuesto de un viaje a [destino] de [días] días para [personas]: vuelos, alojamiento, comida, transporte y actividades.'),

  // ── Creatividad ──────────────────────────────────────────────────────
  P('Creatividad', 'Lluvia de ideas', 'Dame 20 ideas originales para [objetivo], de las más seguras a las más atrevidas.'),
  P('Creatividad', 'Relato corto', 'Escribe un relato corto de [género] sobre [premisa], de unas [800] palabras, con un final sorprendente.'),
  P('Creatividad', 'Nombres', 'Propón 20 nombres para [proyecto / marca / mascota] que transmitan [idea], con una línea explicando cada uno.'),
  P('Creatividad', 'Poema', 'Escribe un poema sobre [tema] con tono [tono], en [verso libre / rima].'),
  P('Creatividad', 'Guion de un vídeo corto', 'Escribe el guion de un vídeo corto divertido sobre [tema] para [plataforma].'),

  // ── Vida diaria ──────────────────────────────────────────────────────
  P('Vida diaria', 'Regalo', 'Dame 10 ideas de regalo para [persona] a quien le gusta [aficiones], con un presupuesto de [cantidad].'),
  P('Vida diaria', 'Organizar un evento', 'Ayúdame a organizar [evento] para [personas]: checklist, cronograma, presupuesto y lista de compras.'),
  P('Vida diaria', 'Resolver un conflicto', 'Tengo este conflicto con [persona]: [situación]. Ayúdame a entender ambas posturas y a preparar qué decir.'),
  P('Vida diaria', 'Comparar productos', 'Quiero comprar [producto] con un presupuesto de [cantidad] para [uso]. Qué debo mirar y qué opciones me recomiendas.'),
]

// ── Catálogo en el idioma de la interfaz ─────────────────────────────────
// Cada idioma tiene su archivo con los mismos prompts en el mismo orden; un
// test comprueba que ninguno se desalinea.
import * as EN from './prompts.en.js'
import * as DE from './prompts.de.js'
import * as FR from './prompts.fr.js'
import * as ZH from './prompts.zh.js'

const TRADUCCIONES = { en: EN, de: DE, fr: FR, zh: ZH }

/** Categorías y prompts en el idioma pedido (español si no hay traducción). */
export function catalogFor(lang) {
  const tr = TRADUCCIONES[lang]
  const cats = tr?.CATS || PROMPT_CATEGORIES
  const idx = (c) => PROMPT_CATEGORIES.indexOf(c)
  const prompts = PROMPT_CATALOG.map((p, i) => ({
    cat: cats[idx(p.cat)] || p.cat,
    title: tr?.PROMPTS?.[i]?.[0] || p.title,
    body: tr?.PROMPTS?.[i]?.[1] || p.body,
  }))
  return { categories: cats, prompts }
}
