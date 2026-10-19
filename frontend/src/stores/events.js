/**
 * events.js — Bus de eventos ligero entre paneles.
 *
 * Las analíticas y el panel de componentes deben reflejar los cambios que el
 * usuario hace en otras pantallas (activar un conector, indexar un documento,
 * votar una respuesta) sin esperar al siguiente sondeo periódico. Un bus
 * mínimo evita tener que enlazar paneles entre sí o subir todo el estado a un
 * ancestro común.
 */
const listeners = new Map()

/** Suscribe a un evento. Devuelve la función para cancelar la suscripción. */
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set())
  listeners.get(event).add(fn)
  return () => listeners.get(event)?.delete(fn)
}

/** Emite un evento. Un listener que falle no puede impedir que corran los demás. */
export function emit(event, payload) {
  for (const fn of listeners.get(event) || []) {
    try { fn(payload) } catch (e) { console.error(`[events] ${event}:`, e) }
  }
}

/** Evento único: algo del sistema cambió y los paneles de estado deben releer. */
export const SYSTEM_CHANGED = 'system:changed'

/** Atajo para notificar un cambio de estado del sistema. */
export function notifyChange(what) {
  emit(SYSTEM_CHANGED, what)
}
