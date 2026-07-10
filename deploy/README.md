# Andromeda — Infraestructura MLOps

Esta carpeta reúne la infraestructura de despliegue y observabilidad de Andromeda.
Cada pieza es funcional y reproducible, pensada para demostrar prácticas reales de
MLOps sobre un sistema de inferencia LLM local-first.

## 1. CI/CD — GitHub Actions

`.github/workflows/ci.yml` se ejecuta en cada push y pull request:

- **Backend tests**: la suite de `pytest` (136 tests) en Python 3.12.
- **Lint**: `ruff` sobre `backend/app`.
- **Frontend build**: `npm ci && npm run build`, comprueba que el artefacto existe.
- **K8s validate**: valida los manifiestos con `kubeconform`.
- **Docker build**: construye las imágenes de backend y frontend.

`.github/workflows/release.yml` construye los binarios de escritorio al etiquetar una versión.

## 2. Kubernetes — `deploy/k8s/`

Despliegue completo del stack en un clúster:

```bash
kubectl apply -k deploy/k8s/
```

Incluye: `Namespace`, `ConfigMap`, Ollama (`Deployment` + `Service` + `PersistentVolumeClaim`),
backend (`Deployment` 2 réplicas + `Service`), frontend (`Deployment` + `Service`),
`Ingress` (enruta `/` al frontend y `/api` al backend) y un `HorizontalPodAutoscaler`
que escala el backend de 2 a 8 réplicas según CPU.

Los pods del backend llevan anotaciones `prometheus.io/scrape` para descubrimiento automático.

## 3. Monitorización — Prometheus + Grafana — `deploy/monitoring/`

El backend expone métricas en `/metrics` en formato de exposición Prometheus
(sin dependencias extra; ver `backend/app/observability/prometheus.py`).

```bash
cd deploy/monitoring
docker compose -f docker-compose.monitoring.yml up -d
```

- **Prometheus** en `http://localhost:9090` scrapea el backend cada 15s y evalúa
  las **reglas de alerta** de `alerts.yml`: backend caído, tasa de éxito < 80%,
  latencia p95 > 15s, degradación > 30%.
- **Grafana** en `http://localhost:3000` (admin/admin) con el dashboard "Andromeda"
  ya provisionado: peticiones, tasa de éxito, latencia p50/p95/p99, degradación,
  uso de herramientas y resultados de A/B.

Métricas: `andromeda_up`, `andromeda_build_info{version}`, `andromeda_requests_total`,
`andromeda_success_rate`, `andromeda_latency_ms{quantile}`, `andromeda_degradation_rate`,
`andromeda_tool_calls_total{tool}`, `andromeda_ab_requests_total{experiment,variant}`.

## 4. Versionado de modelos — MLflow — `deploy/mlflow/`

```bash
cd deploy/mlflow
docker compose -f docker-compose.mlflow.yml up -d   # UI en http://localhost:5001
```

Luego se activa en Andromeda:

```bash
export ANDROMEDA_MLFLOW_ENABLED=true
export ANDROMEDA_MLFLOW_TRACKING_URI=http://localhost:5001
```

Cada inferencia se registra como un run con parámetros (modelo, estrategia, tier de
hardware) y métricas (latencia, ttft, éxito). Es opcional y a prueba de fallos: si
el servidor no responde, la app sigue funcionando (`backend/app/mlops/mlflow_client.py`).

## 5. A/B testing — `backend/app/mlops/ab_testing.py`

Framework para comparar modelos en producción. Se crea un experimento con dos
variantes y un reparto de tráfico; la asignación es determinista por petición
(hash, respetando pesos) y cada resultado se acumula por variante.

```bash
# Crear un experimento: 50% mistral, 50% qwen
curl -X POST http://localhost:8000/api/ab -H "Content-Type: application/json" -d '{
  "id": "mistral-vs-qwen",
  "variants": [
    {"name": "A", "model": "mistral:7b",       "weight": 50},
    {"name": "B", "model": "qwen2.5-coder:7b", "weight": 50}
  ]
}'

# Ver resultados (tasa de éxito, latencia media, ganador)
curl http://localhost:8000/api/ab/mistral-vs-qwen/results
```

Mientras el experimento está activo, las peticiones que no fuerzan modelo se
reparten entre las variantes y los resultados se exponen también en `/metrics`
para visualizarlos en Grafana.

**Rigor estadístico**: el veredicto no es "a ojo". `backend/app/mlops/stats.py`
aplica un test z de dos proporciones y solo declara un ganador con confianza si
(a) hay muestra suficiente (≥30 por variante) y (b) la diferencia es significativa
(p < 0.05). Hasta entonces solo se muestra el "líder" provisional. Hay UI para
gestionar experimentos en Ajustes → A/B Testing.

## Hardening de Kubernetes

Los manifiestos incluyen prácticas de producción: `securityContext` (no-root,
sin escalado de privilegios, capabilities eliminadas), `PodDisruptionBudget`,
`NetworkPolicy` (mínimo privilegio de red), `HorizontalPodAutoscaler` y un
`ServiceMonitor` para el Prometheus Operator.

## Comparar modelos registrados en MLflow

```bash
python scripts/mlflow_compare.py --uri http://localhost:5001
```

Agrupa los runs por modelo y muestra latencia media, ttft y tasa de éxito — la
cara analítica del versionado de modelos.

## 6. Evaluación de calidad — feedback + golden set

El éxito y la latencia dicen si la inferencia terminó y fue rápida, **no si la
respuesta es buena**. Para medir calidad hay dos capas:

**Online (en producción):** cada respuesta lleva botones 👍/👎. El voto se guarda
(`backend/app/mlops/feedback.py`, API `/api/feedback`) y, si la respuesta formó
parte de un experimento A/B, cuenta como señal de calidad de esa variante. Así el
A/B compara modelos por **satisfacción real**, no solo por que no fallaran. La UI
de A/B muestra una barra de satisfacción además de la de éxito.

**Offline (antes de desplegar):** un harness LLM-as-judge evalúa un modelo contra
un conjunto dorado:

```bash
python eval/quality_eval.py --model mistral:7b --judge llama3:8b --json informe.json
```

Para cada prompt de `eval/golden_set.jsonl` envía la pregunta al modelo, pide a un
modelo juez que puntúe la respuesta de 1 a 5 según un criterio, y agrega un score
global por categoría (factual, razonamiento, código, resumen, seguridad…). Es el
patrón estándar para evaluar LLMs sin etiquetar a mano, y se puede correr en CI
para no desplegar un modelo que empeora la calidad.

## 7. Model Registry — versionado y promoción a producción

El registro de runs (MLflow) responde *qué se probó*; el Model Registry responde
*qué está en producción*. Es la pieza que cierra el ciclo de vida del modelo para
un producto de inferencia:

```
evaluar (golden set) → registrar versión con su score → staging → production → SERVIR
```

- **Backend:** `backend/app/mlops/registry.py` (versiones con estado
  none/staging/production/archived; solo una en producción a la vez — promover
  otra archiva la anterior). API en `backend/app/routes/registry.py`:
  `GET/POST /api/registry`, `POST /api/registry/{id}/promote`,
  `GET /api/registry/production`, `DELETE /api/registry/{id}`.
- **Servir producción:** con el toggle `andromeda_serve_production` activo, cuando
  no hay modelo forzado ni A/B activo, el chat sirve exactamente el modelo
  promovido a producción. El bucle MLOps queda cerrado de verdad.
- **Conexión con la evaluación:** `python eval/quality_eval.py --model X --judge Y
  --register` evalúa el modelo y lo registra automáticamente con su score, listo
  para promover si supera al actual.
- **UI:** Configuración → Model Registry (registrar, promover, archivar, ver la
  versión en producción).

Flujo completo demostrable: evalúas un modelo nuevo → si su score supera al de
producción, lo promueves → la app empieza a servirlo → la satisfacción (👍/👎) y
las métricas en producción confirman (o no) la mejora → si empeora, lo archivas y
vuelves al anterior. Ese es el ciclo que distingue a un MLOps.

## 8. Histórico de calidad, drift y SLO

Las métricas instantáneas dicen cómo va *ahora*; esto guarda cómo ha ido *en el
tiempo* para detectar **degradación (drift)** y comprobar **SLOs**. Es lo que
separa "tengo un dashboard" de "vigilo la salud del servicio y sé cuándo empeora".

- **Backend:** `backend/app/mlops/quality_history.py` toma una foto periódica
  (éxito, p50/p95, satisfacción) — una por cubo de 5 min — y evalúa contra
  umbrales SLO (`success_rate >= 95%`, `p95 <= 8s`, `satisfacción >= 70%`).
  Detecta drift comparando la ventana reciente con la anterior (improving /
  stable / degrading). Endpoint `GET /api/traces/quality/history`.
- **Captura:** una tarea de fondo toma snapshot cada 5 min, y también se captura
  al consultar el endpoint (como un scrape de Prometheus) y al apagar la app.
- **UI:** en Analytics, sección "Calidad y SLO en el tiempo": tarjetas de estado
  SLO (verde dentro / rojo fuera) con flecha de tendencia, gráficas de
  satisfacción y latencia p95 en el tiempo, y aviso si se incumple algún SLO.

Con esto el bucle de monitorización queda cerrado: sirves un modelo de producción
(registry), mides su calidad real (feedback + A/B), y si la satisfacción cae o la
latencia sube por encima del SLO, lo ves en la tendencia y puedes archivar la
versión y volver a la anterior.
