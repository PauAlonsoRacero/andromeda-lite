# Retirar el panel de diagnóstico antes de publicar

El panel de diagnóstico es una herramienta de desarrollo. **No debe ir visible
en la versión publicada**: expone los prompts completos de la sesión y las
variables de entorno del equipo.

## Opción A — ocultarlo (recomendada)

Un solo cambio en `backend/app/routes/diagnostics.py`, función `get_state()`:

```python
# Sustituir esta línea:
estado["available"] = os.environ.get(
    "ANDROMEDA_DIAGNOSTICS", "").lower() not in ("0", "false", "off")

# Por esta (ya está comentada justo encima):
estado["available"] = (
    os.environ.get("ANDROMEDA_DIAGNOSTICS", "").lower() in ("1", "true", "on")
    or diag.is_enabled()
)
```

El panel desaparece del menú, pero sigue disponible para quien lo necesite
arrancando con `ANDROMEDA_DIAGNOSTICS=1`. Es la opción preferible: cuando
alguien reporte un fallo, se le puede pedir el registro sin publicar una
versión nueva.

## Opción B — eliminarlo del todo

Si se decide que no forme parte del producto:

1. Borrar `backend/app/observability/diagnostics.py`
2. Borrar `backend/app/routes/diagnostics.py`
3. Borrar `frontend/src/components/DiagnosticsPanel.jsx`
4. En `backend/app/__init__.py`, quitar el bloque `include_router` de diagnóstico
5. En `frontend/src/App.jsx`, quitar el `lazy(...)`, la pestaña y `checkDiagnostics()`
6. En `frontend/src/components/Sidebar.jsx`, quitar `NAV_DIAG` y `diagAvailable`
7. En `frontend/src/stores/edition.js`, quitar `diagAvailable` y `checkDiagnostics`
8. Borrar `tests/test_diagnostics.py`
9. Quitar las llamadas `diag.log(...)` de los módulos instrumentados

Las llamadas al registro están escritas para no fallar si el módulo no existe
(cada una tiene su respaldo silencioso), así que borrar los archivos no rompe la
aplicación aunque quede alguna llamada suelta.

## Comprobación antes de publicar

```bash
# El panel NO debe aparecer por defecto
curl -s http://localhost:8765/api/diagnostics | grep '"available"'
# esperado: "available": false
```
