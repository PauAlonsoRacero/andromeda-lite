# Andromeda — Script de Demo

## Preparación (5 min antes)

```bash
bash scripts/demo.sh   # arranca servicios, warmup de modelos, verifica health
```

Verifica que ves en el terminal:
- `Sistema: ok`
- `Especialistas activos: N` (al menos 2)

---

## Demo de 10 minutos

### 0:00 — Abrir la UI y mostrar el contexto

Abrir `http://localhost`. Señalar en el sidebar:
- Badge de tier: **T2** (verde) con la GPU detectada y los GB de VRAM
- Lista de especialistas activos con sus modelos asignados

**Frase clave**: *"Lo primero que hace Andromeda al arrancar es detectar tu hardware y decidir cómo se va a comportar. Aquí ves T2 — 16 GB. Eso determina cuántos modelos puede ejecutar en paralelo y qué estrategias tiene disponibles. No hay configuración manual."*

---

### 0:30 — Primera petición: code review con bug de seguridad

Escribe en el chat (estrategia: **Auto**):
```
Review this Python code for security issues:

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
```

Mientras genera, señalar:
- Los tokens aparecen en tiempo real (SSE streaming)
- El badge del especialista activo debajo del input
- El spinner en el botón de envío

**Frase clave**: *"Mientras el modelo genera, los tokens llegan token a token. No esperamos a que termine para mostrar algo."*

---

### 1:30 — Mostrar el trace del request anterior

El trace viewer se expande automáticamente debajo del mensaje. Señalar:
- Estrategia: `iterative_refine`
- Especialistas: `software-engineering` + `verifier`  
- Latencias individuales de cada especialista
- `degraded: false` — el hardware tenía suficiente VRAM

**Frase clave**: *"Aquí puedes ver exactamente qué modelos respondieron, cuánto tardó cada uno, y si el sistema tuvo que ajustar algo por el hardware. Esto es lo que hace que sea auditable."*

---

### 2:30 — Simular degradación: cambiar a T1

En otra terminal:
```bash
# Simular que el hardware está al límite
curl -X PUT http://localhost:8000/api/health/simulate-t1 2>/dev/null || true
```

O mostrar directamente via `config/hardware_policies.yaml` que T1 limita a 1 especialista.

Enviar el mismo prompt. Señalar en el trace:
- Ahora `degraded: true`  
- `degradation_reason: "VRAM libre X GB < threshold Y GB"`
- Solo 1 especialista en lugar de 2
- Estrategia bajada a `single`

**Frase clave**: *"Con 8 GB, el sistema no puede usar 2 modelos en paralelo. Se adapta automáticamente — no se rompe, no hay que reconfigurar nada. Usa lo que tiene."*

---

### 3:30 — Mostrar el API Docs

Abrir `http://localhost:8000/docs` en otra pestaña. Señalar:
- Todos los endpoints con schemas
- `POST /api/chat` — el endpoint principal
- `GET /api/health/hardware` — el hardware detectado
- `GET /api/traces/{request_id}` — para auditoría

**Frase clave**: *"Esto no es un chatbot. Tiene una API documentada. Cualquier sistema interno puede llamarlo."*

---

### 4:30 — Mostrar MLOps summary

```bash
curl http://localhost:8000/api/mlops/summary | python3 -m json.tool
```

Señalar:
- Total de runs, success rate
- Distribución de estrategias usadas
- Model registry con latencias promedio por modelo

**Frase clave**: *"Cada petición queda registrada como un run de MLOps. Puedes ver qué modelos funcionan mejor para cada especialista con datos reales de uso."*

---

### 5:30 — Mostrar un ADR

Abrir `docs/adr/ADR-001-fastapi-vs-flask.md`. Señalar que cada decisión técnica importante está documentada con contexto, razones y alternativas consideradas.

**Frase clave**: *"Cada decisión importante tiene su ADR. No porque sea obligatorio, sino porque refleja cómo se piensa este sistema."*

---

### 6:00 — Cierre

**Frase final**: *"Todo corre en tu infraestructura. Cero bytes salen de tu red. El mismo sistema funciona en un portátil de 8 GB o en un servidor de 128 GB sin cambiar configuración. Y cada respuesta es auditable."*

---

## Preguntas frecuentes durante la demo

**"¿Qué pasa si Ollama se cae?"**
→ `GET /api/health` retorna `status: down` inmediatamente. El sistema no crashea.

**"¿Se puede integrar con nuestro sistema interno?"**
→ Sí. `POST /api/chat` es un endpoint REST estándar. Ver `/docs`.

**"¿Qué tan rápido es?"**
→ Depende del hardware. En T2 con `iterative_refine`: 15-25 segundos. Con `latency_first`: 5-10 segundos.
