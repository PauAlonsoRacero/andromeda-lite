/**
 * errors.js — Mensajes de error legibles y visibles.
 *
 * Dos problemas que resuelve:
 *
 * 1. El backend devolvía los errores en español fijo. Ahora envía `error_key`
 *    (una clave i18n) y aquí se traduce al idioma de la interfaz.
 *
 * 2. De 97 llamadas HTTP del frontend, 21 tenían el `catch` vacío: si fallaba
 *    la petición no pasaba nada visible y el usuario veía la aplicación "no
 *    hacer nada" sin ninguna pista de por qué.
 */
import { t } from '../stores/i18n.js'

/**
 * Convierte cualquier error de axios en un texto legible para el usuario.
 * @param {unknown} err  el error capturado
 * @param {string} [fallbackKey]  clave i18n a usar si no hay información útil
 */
export function errorMessage(err, fallbackKey = 'err.generic') {
  const data = err?.response?.data

  // Preferente: clave i18n enviada por el backend
  if (data?.error_key) {
    const texto = t(data.error_key)
    // Si la clave no existe en el idioma actual, t() devuelve la propia clave
    if (texto && texto !== data.error_key) return texto
  }
  // Mensaje ya legible (errores antiguos o de terceros)
  if (typeof data?.error === 'string' && data.error) return data.error
  if (typeof data?.message === 'string' && data.message) return data.message

  // Sin respuesta del servidor: casi siempre el backend no está arrancado
  if (err?.code === 'ERR_NETWORK' || !err?.response) return t('err.no_connection')

  const status = err?.response?.status
  if (status === 401 || status === 403) return t('err.not_authenticated')
  if (status === 404) return t('err.not_found')
  if (status === 413) return t('err.too_large')
  if (status >= 500) return t('err.server')

  return t(fallbackKey)
}

/** Envuelve una promesa y devuelve [datos, mensajeDeError]. */
export async function tryRequest(promesa, fallbackKey) {
  try {
    return [await promesa, null]
  } catch (err) {
    return [null, errorMessage(err, fallbackKey)]
  }
}
