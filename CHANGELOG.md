# Changelog

## [1.0.0] — 2026-07-10 · Primera release pública

### Añadido
- **Auto-asignación de niveles de potencia (zero-config)**: los modelos instalados
  en Ollama se mapean automáticamente a low/mid/high/ultra por tamaño; el modelo
  activado por el usuario ancla su nivel. La potencia automática por complejidad
  del prompt funciona sin editar ningún YAML.
- **Herramientas según capacidad del modelo**: cada modelo se clasifica según si
  puede usar herramientas con fiabilidad (crear archivos, MCP); los modelos débiles
  no reciben instrucciones que no sabrían ejecutar. Badge 🔧 en la UI.
- **i18n completo**: 753 claves en ES/EN/DE/ZH/FR, incluidas página de Sistema,
  panel de potencia, analytics y errores del backend.
- **Instalador Windows completo**: detecta e instala en silencio Ollama **y** el
  runtime WebView2; actualización in situ (mismo AppId) conservando datos.
- **Aviso de nuevas versiones** en la app (GitHub Releases, solo lectura).
- **Analytics ampliado**: KPI de TTFT, peticiones/hora y perfil de latencia p50/p95/p99.

### Corregido
- **Perfil de memoria nunca inicializado**: guardar en memoria devolvía 503 y el
  auto-guardado fallaba en silencio. Ahora funciona (con test de regresión).
- **A/B testing**: la API aceptaba solo variantes dict; ahora también strings.
- Precedencia de selección de modelo: forzado > nivel (auto/manual) > respaldo.

## [Anterior] — sprint de hardening + observabilidad

### Añadido
- **Panel de Analytics (Lite)**: observabilidad con gráficos estilo Apple —
  memorias, herramientas MCP (uso/latencia/error rate), latencias p50/p95 y
  tasa de éxito. Auto-refresh cada 5s. Gating en un flag (`analyticsAvailable`).
- **Memoria automática estilo Claude**: extracción de datos clave y preferencias
  durante la conversación, con actualización por tema (lo nuevo reemplaza lo viejo).
- **Herramientas de archivo nativas** (`write_file`, `read_file`, `list_files`)
  sin necesidad de Node.js.
- **Recuperación ante corrupción** de la DB de memoria (backup + restore, verificado).
- **Instalador de Windows** robusto (Inno Setup): limpia cachés, detecta e instala
  Ollama en silencio, versión leída de `VERSION`, desinstalación con datos opcionales.
- **CI de release** (`release.yml`): compila .exe (Windows) y .app (macOS) al taggear.
- **Sincronización de versión** centralizada (`scripts/sync_version.py` + `VERSION`).
- Analytics de herramientas MCP y stats de memoria ampliados (hit rate, tamaño).

### Cambiado
- Gráficos rediseñados con estética Apple (Analytics + StatsPanel de Pro):
  animaciones de entrada, gradientes y tipografía afinada.

### Corregido
- Polling infinito de Ollama (idempotencia + debounce de 30s).
- Ollama offline: reintentos con backoff y mensaje claro.
- Timeout de 30s en herramientas MCP.
- Concurrencia en asignación de modelos (lock + escritura atómica).
- `manager.tools()` usado como método cuando es propiedad (rompía el tool-calling).

### Tests
- 101 backend + 10 de robustez nuevos. Verdes.

## [pre-release interna] — 2026-06

Autodiagnóstico para depurar "la IA no funciona".

### Nuevo: GET /api/health/diagnose
- Verifica TODA la cadena de inferencia paso a paso y dice qué falla:
  1) Ollama conectado, 2) modelos descargados, 3) especialistas activos,
  4) los modelos de los especialistas están descargados, 5) inferencia de
  prueba real contra Ollama.
- Pensado para ver el problema en la máquina del usuario sin leer logs.

### Verificación exhaustiva del flujo
- Confirmado end-to-end (streaming real): modo Auto, modelo forzado, modelos de
  razonamiento con <think>, y el caso de tener un solo modelo descargado (el
  fallback elige correctamente ese modelo). Todo responde.

### Tests
- 139 tests verdes.

## [2.11.0] — 2026-06

Corregido el selector de modelo que se quedaba "pegado".

### El modelo no cambiaba (bug de binding + conflicto de menús)
- El selector del chat usaba `value={...}` con opciones dinámicas, un patrón que
  en SolidJS no actualiza bien la selección. Ahora usa `selected` en cada opción
  y cambia correctamente.
- Además había un conflicto: el modelo forzado del chat pisaba lo que cambiaras
  en el menú ⚙ IAs, dando sensación de "modelo fijo". Ahora:
  · El selector muestra claramente cuándo estás en modo forzado (🔒 resaltado).
  · El menú ⚙ IAs avisa "Estás forzando X" con un botón "Volver a Auto".
  · Aplicar cambios en el menú de IAs desactiva el modelo forzado
    automáticamente (vuelves a orquestación).

### Tests
- 138 tests verdes.

## [2.10.0] — 2026-06

Fallback de modelo más sensato + gráficos nuevos en Estadísticas/MLOps.

### Corregido el fallback que tiraba a codellama
- Cuando el modelo preferido no está descargado, el fallback elegía el primer
  modelo por orden alfabético (codellama ganaba por la 'c'). Ahora elige el
  modelo MÁS GRANDE disponible (por tamaño del tag, p. ej. :32b > :7b), que es
  una elección mucho más razonable.
- Defensa extra: el modelo forzado se propaga también en la config de streaming.

### Gráficos nuevos (MLOps)
- Barras de "Uso por modelo" (cuántas veces respondió cada modelo).
- Barras de "Latencia media por modelo" (comparativa visual, con color por
  rapidez).
- "Fallos por estrategia" (fallidos / total) para diagnóstico.

### Tests
- 138 tests verdes (nuevo: fallback elige el modelo más grande, no alfabético).

## [2.9.0] — 2026-06

Modelo forzado a prueba de balas + insignia del modelo en cada respuesta.

### El bug de fondo (el fallback, como sospechaba el usuario)
- Al forzar un modelo, el código pasaba igualmente por build_plan, cuyo
  *fallback* (cuando no hay clasificación) activaba TODOS los especialistas y
  resolvía sus modelos (codellama, etc.), sumándoles uso.
- Ahora, si fuerzas un modelo, se construye un plan directo de UNA sola IA con
  ese modelo, SIN pasar por build_plan ni el fallback. Verificado con la
  configuración real (orquestador codellama): 3 peticiones forzadas → solo se
  llama a qwen3:32b, codellama no sube en estadísticas ni MLOps.

### Insignia del modelo en la respuesta
- Cada respuesta muestra, junto al especialista, el modelo real que respondió
  (p. ej. "generalist · qwen3:32b"), no solo el tipo de agente.

### Tests
- 137 tests verdes.

## [2.8.0] — 2026-06

Corregido el modelo forzado: ahora se usa de verdad y se reporta bien.

### Bug resuelto (reportado en uso real)
- Al forzar un modelo (p. ej. qwen3:32b) el clasificador interno seguía
  ejecutándose con el modelo orquestador (codellama:7b en algunas configs),
  sumándole usos y enmascarando el modelo elegido. Ahora, si fuerzas un modelo,
  el clasificador NO se ejecuta: la petición va directa a ese modelo.
- El especialista reportado al forzar un modelo es siempre "generalist", para
  un reporte coherente en Estadísticas y MLOps.
- Verificado: una petición forzada solo llama al modelo elegido (ninguna llamada
  interna a otro modelo durante la petición).

### Tests
- 137 tests verdes (nuevo: forzar modelo no dispara el clasificador).

## [2.7.0] — 2026-06

Plug & play de modelos verificado de extremo a extremo.

### Cualquier modelo descargado funciona sin configurar nada
- Descargas un modelo en Ollama → aparece solo en el selector del chat (se
  refresca cada 20s, sin reiniciar Andromeda).
- Lo seleccionas → se usa de inmediato (sin editar specialists.yaml).
- Su uso queda reflejado automáticamente en Estadísticas y en MLOps
  (con nombre de modelo, latencia, tier y contador de usos).

### Tests
- 136 tests verdes (4 nuevos: test de integración del flujo plug & play que
  blinda selector → uso → estadísticas → MLOps).

## [2.6.0] — 2026-06

Selector de modelo manual + reporte de modelo en estadísticas.

### Elegir cualquier modelo de Ollama desde el chat
- Nuevo selector en la barra del chat: "⚡ Auto (orquesta)" o cualquier modelo
  instalado en Ollama (p. ej. qwen3:32b recién descargado), sin editar YAML.
- Campo `force_model` en la API: fuerza un modelo concreto para toda la
  respuesta, saltándose el enrutamiento por tiers.
- Antes, un modelo descargado por tu cuenta no aparecía en el selector ni se
  podía usar salvo añadiéndolo a specialists.yaml.

### Estadísticas: ahora se reporta el modelo usado
- La metadata final incluye `models_used` (especialista → modelo real), así que
  las estadísticas muestran qué modelo respondió. Antes salía vacío.

### Tests
- 132 tests verdes.

## [2.5.0] — 2026-06

Acceso al sistema de archivos (file system access) — como Claude, pero en local.

### Nuevo: workspace de archivos
- Andromeda puede crear, leer, modificar, mover y borrar archivos en local.
- API REST completa en `/api/files` (write, read, list, mkdir, move, delete, restore).
- La IA puede actuar sobre archivos desde el chat emitiendo bloques
  ```andromeda:write|mkdir|delete|move``` que el backend detecta y ejecuta.
- **Borrado reversible**: por defecto va a una papelera interna; el borrado
  permanente requiere confirmación explícita.
- **Seguridad**: todas las operaciones quedan confinadas al workspace; se
  bloquean rutas absolutas, "..", y cualquier intento de escapar del directorio.
- Workspace configurable con `ANDROMEDA_WORKSPACE` (por defecto ~/Andromeda_Files).

### Material de lanzamiento
- Gráficos comparativos profesionales (Andromeda vs IAs cloud, coste anual,
  diagrama de orquestación, métricas del enrutador) en `docs/launch/graficos/`.

### Tests
- 131 tests verdes (24 nuevos: workspace, parser de acciones y seguridad).

## [2.4.0] — 2026-06

Búsqueda web y visión conectadas al chat (a partir de pruebas reales).

### Búsqueda web mucho más útil
- `needs_web_search` ahora detecta eventos, deportes, resultados, personas y datos cambiantes ("cómo ha quedado España en el mundial" ya dispara la búsqueda; antes no).
- El contexto web inyectado refuerza al modelo para que se base en los resultados reales y NO invente datos que los contradigan.

### Imágenes conectadas al chat
- Si adjuntas una imagen, un modelo de visión (llava) la describe primero y esa descripción se inyecta en el prompt para que el resto del pipeline razone sobre ella. Antes las imágenes se enviaban pero el chat las ignoraba. (Requiere `ollama pull llava:7b`.)

### Tests
- 107 tests verdes.

## [2.3.0] — 2026-06

Banco de pruebas masivamente ampliado — fiabilidad del enrutamiento reforzada.

### Más casos, más fiable
- Dataset de entrenamiento: 28 → **51 casos**; holdout: 12 → **24 casos** (75 en total), cubriendo mucha más variedad de fraseo, longitud y dificultad por dominio.
- Nuevos desempates de dominio que generalizan:
  - Preguntas informativas ("para qué se usa X", "qué significa X") → factual aunque X sea técnico.
  - "demuestra/demostración" → reasoning aunque el objeto sea un algoritmo.
  - Verbos de prosa (ensayo, artículo, introducción) → writing, salvo que se pida resumir.
- **Señales de alta exigencia**: tareas intrínsecamente difíciles (demostrar un teorema, diseñar un compilador, parser recursivo) escalan a tier 3-4 aunque el prompt sea corto — antes se quedaban en tier 2.
- Más señales por dominio (devops, integral/derivada/tautología en reasoning, etc.).

### Resultados medidos
- Entrenamiento (51 casos): **100% / 100% / 100%** (dominio / especialista / tier).
- Validación (24 casos nuevos): **96% / 96% / 96%**, error medio de tier 0.04.
- Los 2 fallos restantes del holdout son casos genuinamente ambiguos (etiqueta opinable), no errores claros — no se fuerzan para evitar sobreajuste.

### Tests de regresión más estrictos
- Umbrales subidos a 0.95 (entrenamiento) y 0.90 (validación): si un cambio degrada el enrutamiento por debajo, la CI falla.
- 106 tests verdes.

## [2.2.0] — 2026-06

Clasificador más robusto + banco de pruebas ampliado.

### Clasificador (matching robusto)
- Las keywords cortas (≤4 letras como "api", "go", "sql") ahora matchean por token exacto, no por subcadena — elimina falsos positivos como "api" dentro de "capital".
- Matching insensible a acentos: "función" y "funcion" se tratan igual.

### Banco de pruebas ampliado
- Dataset de entrenamiento de 20 → 28 casos, con más variedad (CI/CD, recetas, traducción, tests, preguntas de diferencia).
- Más señales de dominio guiadas por los nuevos casos: factual ("diferencia entre", "receta", "para qué sirve") y devops en code ("pipeline", "ci/cd", "docker", "kubernetes", "deploy").
- **Resultados:** entrenamiento 100%/100%/100%, holdout 100%/100%/92% (sin sobreajuste).

### Tests
- 106 tests verdes (antes 104): robustez del clasificador (sin falsos positivos, insensible a acentos).

## [2.1.0] — 2026-06

Escalado por reintento + material de lanzamiento + limpieza.

### Escalado por reintento (cierra el círculo de Andromeda Orquesta)
- Con 1 IA y `ANDROMEDA_ESCALATION=1`: si la respuesta tiene baja confianza y queda margen de tier, Andromeda **reintenta una vez con el modelo del tier superior** y se queda con la mejor de las dos.
- Es la materialización de "subir escalafones de potencia a conveniencia": se gasta lo mínimo por defecto y solo se escala cuando hace falta.
- Opt-in (desactivado por defecto, porque el reintento añade latencia al saltar).
- Verificado E2E: respuesta floja en tier bajo → reintenta y muestra la respuesta del tier superior.

### Material de lanzamiento (nuevo)
- `docs/launch/GUIA_LANZAMIENTO.md`: plan completo para GitHub + LinkedIn + r/LocalLLaMA, con cómo grabar el GIF.
- `docs/launch/LINKEDIN.md`: post listo (versión larga y corta) enfocado a mostrar aprendizaje técnico.
- README con sección dedicada a Andromeda Orquesta y tabla de métricas del enrutamiento.

### Limpieza y rigor
- Auditoría de código muerto (vulture) y archivos obsoletos: sin hallazgos reales (los dos middlewares y todos los routers se usan).
- Verificada la eficiencia del orquestador: ~0.05ms por decisión, sin overhead notable.
- 104 tests verdes. Lint estricto limpio.

## [2.0.0] — 2026-06

Andromeda Orquesta con confianza, transparencia y documentación.

### Estimación de confianza (nuevo)
- **`core/confidence.py`**: estima la calidad de cada respuesta con una heurística barata (sin coste de LLM) — detecta respuestas evasivas, presentaciones en vez de respuestas, repetición y truncamiento.
- La confianza se expone en la metadata del chat y se muestra en la UI con un indicador (●/◐/○ + %).
- `should_escalate()`: decide si valdría la pena reintentar en un tier superior (base del escalado por reintento).

### Transparencia del orquestador (nuevo)
- **`POST /api/orchestra/explain`**: explica qué haría el orquestador con un prompt (dominio, complejidad, tier, especialistas, estrategia) SIN ejecutarlo. Ideal para depurar y para demos.

### Robustez verificada
- Confirmado que Andromeda degrada con gracia cuando Ollama falla a mitad (no se cuelga ni da 500).

### Documentación
- **`docs/ORQUESTA.md`**: arquitectura completa del orquestador, pipeline de decisión, tabla de ejemplos medidos y límites honestos.

### Calidad
- 102 tests verdes (antes 99). Lint estricto limpio (F, E7xx).

## [1.9.0] — 2026-06

Banco de pruebas del enrutamiento + Andromeda Orquesta afinado con datos.

### Banco de pruebas (nuevo)
- **`eval/eval_routing.py`**: mide si el orquestador decide bien (dominio, especialista, tier de potencia) sin necesitar modelos ni Ollama — evalúa la capa de política directamente.
- Dos datasets etiquetados: `routing_dataset.jsonl` (20 casos, entrenamiento) y `routing_holdout.jsonl` (12 casos nuevos, validación) para detectar sobreajuste.
- **`GET /api/orchestra/eval`**: expone las métricas de calidad del enrutamiento desde la API.
- Tests de regresión (`test_routing_eval.py`): si un cambio futuro degrada el enrutamiento, la CI falla.

### Andromeda Orquesta afinado con evidencia
Mejoras guiadas por las métricas, no a ojo:
- Señales de dominio ampliadas y con normalización de acentos ("cuál" → "cual").
- Desempate de intención: "resumir/enumerar" → summarizer aunque mencione "artículo".
- Señal de *output extenso*: pedir un ensayo/historia/parser sube la potencia aunque el prompt sea corto (generar mucho contenido de calidad es exigente).
- Suelo de potencia por dominio afinado.

**Resultados medidos:**
- Entrenamiento: dominio 100%, especialista 100%, tier 100% (desde 75% inicial).
- Validación (casos nuevos): dominio 100%, especialista 100%, tier 92%, error medio de tier 0.08.

### Tests
- 97 tests verdes (antes 95), incluidos los de regresión del enrutamiento.

## [1.8.0] — 2026-06

**Andromeda Orquesta** — escalado de potencia y enrutamiento automáticos.

La filosofía: en vez de un único modelo gigante, el orquestador elige solo el
módulo del tamaño justo y el especialista adecuado para cada prompt, escalando
la potencia solo cuando la tarea lo exige. Máxima eficiencia, sin que el usuario
tenga que configurar nada (aunque puede).

### Escalado de potencia (power tiers 1-4)
- El orquestador deriva un **tier de potencia** combinando dos señales:
  - **Complejidad** del prompt (longitud, profundidad, nº de preguntas).
  - **Dominio** de la tarea (código, razonamiento, redacción, datos, charla), cada uno con su propio peso.
- Resultado: un "demuestra que √2 es irracional" (corto pero exigente) escala a un modelo mediano, mientras una charla larga se queda en el más pequeño. El tamaño justo para cada caso.
- Nuevo `best_for_power()`: elige el modelo más pequeño que basta para el tier pedido, acotado por hardware y VRAM. Nunca malgasta un 32B en un "hola".
- Suelo de potencia por dominio: razonar o programar arrancan en tier 2 aunque el prompt sea corto.

### Enrutamiento por especialista
- Al detectar el dominio, el orquestador **prioriza el especialista idóneo**: código → software-engineering, redacción → technical-writer, etc. Materializa la idea de "una IA para escribir, otra para ingeniería".

### Transparencia
- La UI muestra un badge **⚡T{1-4}** en cada respuesta con la potencia elegida y la complejidad detectada (tooltip).

### Tests
- 95 tests: detección de dominio (incluido el falso positivo "capital"→code), suelo de potencia, y escalado por complejidad+dominio.

### Nota honesta de alcance
- Esto NO iguala a un modelo de 600B en general — sí acerca mucho en tareas concretas donde un modelo especializado del tamaño justo rinde como uno grande, gastando una fracción de la memoria. Es el primer paso; la precisión del enrutamiento se irá ampliando.

## [1.7.0] — 2026-06

Pulido de calidad de la fusión.

### Fusión más limpia y coherente
- **Eliminada la triple pasada de LLM.** Antes, en multi-IA, el texto pasaba por: fusión → interpretación → IA de salida (3 pasadas). Con modelos pequeños cada pasada añadía ruido y degradaba la respuesta. Ahora, cuando actúa la IA de salida, se omite la pasada de interpretación intermedia: fusión → IA de salida (2 pasadas). Respuestas más coherentes.

### Detalles de UX
- El menú "exportar" se cierra al hacer clic fuera (antes quedaba abierto).

### Verificación
- 91 tests verdes; los 48 endpoints GET responden; lint limpio.
- E2E confirmado: 1 IA streaming fluido, multi-IA sin fuga de tokens crudos, generación de documentos, y registro de actividad.

## [1.6.0] — 2026-06

Creación de archivos reales + orquestador más inteligente.

### Crear archivos (Word, Excel, PDF)
- **Nuevo endpoint `/api/documents/generate`**: convierte cualquier respuesta en un archivo real descargable — Word (.docx), Excel (.xlsx), PDF y Markdown. Soporta encabezados, listas, negrita, tablas y bloques de código.
- Menú "📄 exportar" en cada respuesta del chat (Word / PDF / Excel) + descarga directa de bloques de código con su extensión.

### Orquestador más inteligente
- **Detector de complejidad del prompt**: combina longitud, señales de profundidad/técnicas/creativas y nº de preguntas para puntuar la dificultad en [0,1].
- El nº de IAs se decide automáticamente según esa complejidad: trivial → 1 IA; medio → 2; complejo → hasta 4 (acotado por hardware y relevancia). El usuario ya no necesita elegir manualmente, aunque sigue pudiendo.

### Actividad reciente (arreglo)
- El chat ahora **guarda cada interacción como trace** en SQLite. Antes la pantalla de "Actividad reciente" estaba siempre vacía porque solo se registraba en MLOps, no en el store de traces.

### Tests
- 91 tests (antes 87): generación de los 4 formatos de documento, rechazo de contenido vacío, y escalado del orquestador por complejidad.

## [1.5.0] — 2026-06

Arreglos de UX a partir de pruebas reales de usuario.

### Fusión multi-IA (arreglo importante)
- **Ya no se muestran los tokens crudos intercalados.** Antes, con varias IAs, sus respuestas aparecían mezcladas carácter a carácter (ilegible). Ahora, en multi-IA, la fusión ocurre en backend mostrando solo un indicador de progreso ("N IAs colaborando…"), y al terminar se streamea únicamente la respuesta final limpia (IA de salida o fusión).
- El streaming token a token en vivo se mantiene cuando hay 1 sola IA (experiencia fluida).

### Selección y descarga
- **Selección de texto arreglada**: el chat ahora permite seleccionar y copiar texto (pywebview lo bloqueaba; forzado con CSS).
- **Botón de descarga en bloques de código**: cada bloque se puede bajar con la extensión correcta (.py, .js, .sql, etc.).
- **Descargar respuesta como Markdown**: botón en el pie de cada respuesta para guardarla como .md.

### Calidad de respuestas
- Reescrito el prompt de identidad: los modelos pequeños ya no se presentan ("soy un asistente de Andromeda…") en vez de responder. Ahora van directos a la respuesta.
- System prompt de la IA de salida más exigente: toma lo mejor de cada borrador, entrega código/documentos completos, sin meta-comentarios.

## [1.4.0] — 2026-06

Pulido de producto: la diferencia entre demo y producto profesional.

### Experiencia de usuario
- **Markdown profesional en el chat**: reemplazado el render casero por `marked` + estilos completos. Ahora tablas, listas anidadas, enlaces, citas y encabezados se ven correctamente. Antes el texto con formato parecía roto.
- **Onboarding afinado**: el comando de instalación de modelos ahora detecta si corres en Docker o como app nativa y muestra el correcto (`ollama pull` vs `docker exec`).
- Botón de copiar (mensaje completo y bloques de código) ya presente y funcional.

### Calidad / tests
- **87 tests** (antes 82): nuevo `test_integration.py` con flujos de usuario completos — setup/onboarding, activar/desactivar IAs, listado de modelos, traces y métricas, health.
- Corregida la fixture de test para separar correctamente `tracer` (AndromedaTracer) de `store` (TraceStore), fiel a producción.

### Documentación / publicación
- README con secciones de **capturas** y **benchmarks** listas para rellenar con material real.
- `docs/media/` con instrucciones de qué grabar (GIF de fusión, capturas clave).
- Badges y cifras actualizadas (14 estrategias de fusión, 87 tests).

## [1.3.0] — 2026-06

Calidad de producto y herramientas para publicación.

### Nuevo
- **Banco de pruebas** (`benchmarks/benchmark.py`): mide latencia, TTFT y tokens/s reales sobre tu hardware, y cómo escala de 1 a 4 IAs. Genera `REPORT.md` con tablas y `results.json` para graficar.
- **CONTRIBUTING.md**: guía de desarrollo, arquitectura del pipeline y estilo de código.
- **Diagrama del pipeline de 5 etapas** en el README.

### UX de la IA de salida
- Cuando hay 2+ IAs, la respuesta unificada (etapa 4) es la protagonista; las respuestas individuales de cada IA quedan en un desplegable "Ver respuestas individuales".
- Insignia "✨ unificada" en el pie del mensaje cuando actuó la IA de salida.
- El razonamiento interno (`<think>`) de modelos como deepseek-r1 se filtra en vivo y del resultado.

### Calidad
- CI completo (ya presente): tests backend, lint (ruff), build frontend, build Docker, smoke test.
- 81 tests verdes.

## [1.2.0] — 2026-06

Pipeline de orquestación de 5 etapas.

### Nueva arquitectura
Reformulado el flujo completo a 5 etapas claras y testeables:

    prompt → [1] orquestador → [2] IA(1-4) paralelo → [3] single/fusión
           → [4] IA de salida → respuesta

- **Etapa 1 — Orquestador** (`orchestrator.py`): decide qué IAs, cuántas, qué estrategia y el MODO (rápido/equilibrado/profundo) según el tipo de tarea detectado en el prompt. Toda la política en un solo módulo.
- **Etapa 2 — Ejecución paralela**: las IAs responden en paralelo con streaming real, cada una con un modelo distinto.
- **Etapa 3 — Fusión**: 1 IA → directo; 2+ IAs → estrategia de fusión adaptada (síntesis para creativo, best-of-N para código, votación para respuestas verificables, debate para razonamiento).
- **Etapa 4 — IA de salida** (`output_ai.py`): nueva. Cuando hay 2+ IAs, una pasada final pule y unifica el resultado (tono, coherencia, sin redundancias), en streaming. Con fallback: si falla, entrega la fusión intacta.

### Modos automáticos
El orquestador clasifica el prompt y elige el modo:
- **fast**: tareas simples/saludos → 1 IA, sin overhead.
- **balanced**: código, respuestas verificables → fusión ligera.
- **deep**: ensayos, comparativas, razonamiento → síntesis + IA de salida.

### Tests
- 81 tests (antes 76): pipeline de 5 etapas, selección de modo, IA de salida solo con 2+ IAs, fallback de la IA de salida, código→best_of_n.

## [1.1.0] — 2026-06

Rediseño del sistema de orquestación.

### Orquestación unificada
- **Nuevo `orchestrator.py`**: toda la decisión (qué IAs, cuántas, qué estrategia, qué modelos) se toma ahora en UN solo lugar coherente, en vez de repartida entre chat.py, classifier.py y policy.py con sobrescrituras que se pisaban.
- El número de IAs "natural" se decide por relevancia real: cuántos especialistas superan el umbral relativo al mejor score, acotado por hardware. Antes, forzar N metía especialistas en orden arbitrario del registro.
- Al forzar N IAs, se rellena con los **siguientes mejores del ranking** del clasificador, no con especialistas al azar.
- Estrategia siempre coherente con el nº final de IAs: 1 IA → single; N IAs → la propuesta por el clasificador si fusiona, o parallel_merge por defecto. Imposible acabar con "single" y 3 IAs, o "parallel_merge" con 1.
- Selección manual de especialistas respeta exactamente los elegidos y su orden.
- Reparto de modelos distintos entre especialistas para diversidad real en la fusión.

### Tests
- 76 tests (antes 70): 6 nuevos cubren el orquestador (single para prompt simple, forzar N exacto, modelos distintos, selección manual, estrategia de usuario respetada, 1 IA fuerza single).

## [1.0.1] — 2026-06

Ronda de robustez y calidad.

### Robustez
- Las 14 estrategias de fusión nunca devuelven vacío: si el orquestador falla o no responde, caen a una concatenación coherente de las respuestas. El usuario siempre recibe contenido.
- Fallo parcial en multi-IA: si una IA falla, la respuesta se completa con las que sí funcionaron, sin error global.
- Ollama caído ahora da un mensaje claro y accionable en vez de respuesta vacía.
- Detección de modelos en caliente: descargar un modelo ya no requiere reiniciar; el chat lo detecta en la siguiente petición.

### Calidad del clasificador
- Reequilibrado el scoring de keywords (normalización por tamaño de vocabulario): cada especialista compite en igualdad. Antes 'software-engineering' ganaba casi siempre por tener más términos.
- Ahora prosa→technical-writer, resúmenes→summarizer, código→software-engineering eligen el especialista correcto como primario.

### Tests
- 70 tests (antes 51): cobertura de las 14 estrategias bajo fallo, fallback del orquestador, y precisión del clasificador por dominio.

## [1.0.0] — 2026-06

Primera versión pública.

### Núcleo
- Orquestación multi-especialista con clasificador automático y 12 estrategias de fusión (`parallel_merge`, `confidence_weighted`, `best_of_n`, `iterative_refine`…).
- Motor de políticas hardware-aware: tiers T1–T4, presupuesto VRAM en vivo, reparto de presupuesto al forzar N IAs en paralelo, degradación elegante.
- Auto-activación de especialistas según los modelos descargados en Ollama.
- Soporte completo Apple Silicon (memoria unificada: hasta RAM−4GB como VRAM en M-series ≥32GB; override con `ANDROMEDA_HOST_VRAM_GB`).

### Producto
- App de escritorio nativa: Windows `.exe` + instalador Inno Setup (instala Ollama si falta), macOS `.app`. Ventana frameless con titlebar propio (semáforos en macOS, controles en Windows), splash con fases reales de arranque.
- Lab de IA: variantes de modelo vía Modelfile (parámetros, system prompt, few-shot), datasets JSONL estilo HuggingFace, prueba en vivo y asignación a especialistas.
- MLOps integrado: latencia, TTFT, tokens/s por run; registro por modelo con tasas de éxito; tendencias.
- Catálogo curado de 29 modelos con chequeo de encaje contra tu GPU y progreso de descarga real.
- Cuentas locales opcionales (PBKDF2 + sesiones revocables) con gate de login en escritorio.

### Seguridad
- API solo-loopback, CORS estricto, cabeceras de seguridad, límite de tamaño de body, rate limiting, sandbox de código con timeout duro.

### Correcciones destacadas
- Cierre garantizado de la app en macOS.
- Trap global de errores en el frontend (adiós pantallas negras silenciosas).
- Detección VRAM consistente entre arranque y runtime (nvidia-smi ausente, Docker, Mac).
