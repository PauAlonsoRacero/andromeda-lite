# Benchmarks de Andromeda

Mide el rendimiento real del pipeline de orquestación sobre **tu** hardware.

## Uso

1. Arranca Andromeda (app de escritorio, o `docker-compose up`).
2. Asegúrate de tener Ollama corriendo con al menos un modelo:
   ```bash
   ollama pull llama3.2:3b
   ```
3. Ejecuta el benchmark:
   ```bash
   python benchmarks/benchmark.py --url http://localhost:8000
   ```

## Opciones

| Flag | Por defecto | Descripción |
|------|-------------|-------------|
| `--url` | `http://localhost:8000` | URL del backend de Andromeda |
| `--runs` | `3` | Repeticiones por caso (mediana) |
| `--parallel` | `1,2,3` | Niveles de paralelismo a probar |
| `--prompts` | — | Fichero con prompts propios (uno por línea) |

## Salida

- `benchmarks/REPORT.md` — informe legible con tablas (latencia, TTFT, tok/s por nº de IAs).
- `benchmarks/results.json` — datos crudos para graficar.

## Qué mide

- **Latencia total** y **TTFT** (time-to-first-token) por tipo de tarea.
- **tokens/s** de generación.
- Cómo **escala** al pasar de 1 a 2, 3 o 4 IAs en paralelo.
- Qué **estrategia de fusión** y si se activó la **IA de salida** en cada caso.

Ideal para comparar tu GPU contra otras y para mostrar el coste/beneficio real
de la orquestación multi-IA frente a una sola IA.
