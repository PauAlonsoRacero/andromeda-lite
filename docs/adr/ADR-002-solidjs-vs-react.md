# ADR-002: SolidJS sobre React para el frontend de Andromeda

## Estado
Aceptado — Fase 0

## Contexto

El frontend de Andromeda tiene un patrón de UI muy específico: un chat con streaming de tokens. Durante el streaming, el componente activo recibe 50–200 actualizaciones por respuesta (un token cada vez). El framework elegido determina cómo de eficiente es cada actualización.

**Con React:**
Cada token que llega dispara un re-render del componente que contiene el mensaje activo. Sin optimizaciones manuales (`useMemo`, `useCallback`, `React.memo`), React re-renderiza el árbol completo del chat en cada token. Con optimizaciones, el código se vuelve complejo y frágil.

**Con SolidJS:**
SolidJS usa un modelo de reactividad basado en Signals, sin Virtual DOM. Cuando `streamContent` (un Signal) cambia, **solo el nodo de texto específico que lo consume se actualiza** en el DOM real. El resto de la UI no se toca.

## Decisión

Usamos **SolidJS 1.9+ con Vite 5**.

El patrón clave:
```javascript
// Signal separado para el contenido del stream activo
// Se actualiza token a token — solo StreamingToken consume este signal
const [streamContent, setStreamContent] = createSignal('')

// En el componente del mensaje activo:
// Solo ESTE div se re-evalúa en cada token. Nada más.
<div>{streamContent()}</div>
```

## Consecuencias

**Positivas:**
- Actualizaciones granulares: solo el nodo de texto activo cambia en cada token
- Bundle runtime: ~7 KB vs ~40 KB de React
- Sintaxis JSX compatible — la curva de aprendizaje desde React es mínima
- Sin Virtual DOM: menos overhead de memoria y CPU
- Benchmarks: 8× más rápido que React en actualizaciones de UI intensivas

**Negativas:**
- Ecosistema más pequeño que React (menos librerías de UI, menos ejemplos)
- `createSignal` en lugar de `useState`: diferencia conceptual que requiere adaptación
- Menos desarrolladores con experiencia en SolidJS en el mercado

## Alternativas consideradas

**React 18 + optimizaciones manuales**: viable pero añade complejidad sin resolver el problema de raíz. `useTransition`, `useDeferredValue` y `React.memo` pueden mitigar los re-renders, pero el modelo mental es más difícil y el resultado inferior al de SolidJS.

**Svelte/SvelteKit**: compile-time reactivity, excelente rendimiento. Descartado porque la sintaxis es más diferente de React que SolidJS, lo que aumenta la curva de aprendizaje.

**Vue 3 con Composition API**: buena opción, pero la sintaxis de templates difiere más de JSX que SolidJS. No aporta ventajas claras sobre SolidJS para este caso de uso.
