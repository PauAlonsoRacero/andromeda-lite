# Guía de lanzamiento de Andromeda

Plan para sacar Andromeda al mundo de forma que la gente entienda cómo funciona
y lo pueda probar. Orden pensado por impacto.

## 1. GitHub (lo primero — sin esto el proyecto no existe para nadie)

### Antes de subir
- [ ] Revisa que no haya secretos en el código (`.env`, claves). El `.gitignore` ya excluye `.env`.
- [ ] Graba el GIF de la fusión (ver sección 3) y ponlo en `docs/media/demo-fusion.gif`.
- [ ] Corre el benchmark real en tu RTX y pega los números en el README (`benchmarks/`).

### Estructura que ya verá la gente
- `README.md` — portada con qué es, cómo funciona, Andromeda Orquesta, quickstart.
- `docs/ORQUESTA.md` — arquitectura del orquestador (el diferenciador técnico).
- `eval/` — banco de pruebas del enrutamiento (demuestra rigor).
- `CHANGELOG.md` — historial de versiones (demuestra constancia).
- `CONTRIBUTING.md`, `.github/workflows/ci.yml` — que parezca un proyecto serio.

### El primer commit / release
- Crea el repo público, sube el código.
- Haz un release (v2.0.0) con los binarios (`andromeda_final.zip`, `andromeda_mac.tar.gz`).
- En la descripción del release, enlaza al GIF y a `docs/ORQUESTA.md`.

## 2. LinkedIn (proyección — tu altavoz con ~1.600 seguidores)

- Usa `docs/launch/LINKEDIN.md`.
- Publica el post con el GIF o el diagrama del pipeline.
- Pon el enlace de GitHub en el PRIMER comentario (LinkedIn penaliza enlaces en el post).
- Responde a todos los comentarios las primeras 2h (el algoritmo premia interacción temprana).

## 3. El GIF que vende (lo más importante visualmente)

15-20 segundos mostrando:
1. Escribes una pregunta compleja que active varias IAs y un tier alto.
2. Se ve el indicador "N IAs colaborando…".
3. Aparece la respuesta unificada, con los badges ⚡T3 y de confianza.

Herramienta: ScreenToGif (Windows) o Kap (Mac). Exporta <5MB, 720p, tema oscuro.

## 4. r/LocalLLaMA (opcional, comunidad técnica)

- Tono: "hice esto, aquí está el código, ¿qué opináis?". NUNCA como anuncio.
- Esta comunidad premia lo abierto y honesto. Menciona los límites (no iguala a un 600B).
- Título posible: "I built a local AI orchestrator that auto-scales model size per prompt — measured routing quality, looking for feedback"

## 5. Qué decir cuando pregunten "¿en qué se diferencia de X?"

- vs LM Studio / Jan / Ollama+OpenWebUI: esos corren UN modelo a la vez.
  Andromeda corre un equipo de especialistas y fusiona, y escala la potencia
  por prompt automáticamente.
- Sé honesto: no compite en pulido con productos de equipos enteros. Su valor
  es la orquestación y el escalado medible, todo local y open source.

## Honestidad estratégica

El mayor retorno de este proyecto no es monetizarlo directamente (difícil a corto
plazo). Es lo que demuestra de ti como ingeniero: diseñaste un sistema, lo mediste,
lo validaste y lo documentaste. Eso es exactamente lo que vale para un puesto de
MLOps. Preséntalo como prueba de capacidad, no como producto a vender.
