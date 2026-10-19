// Versión central de Andromeda (frontend).
// Debe coincidir con app_version del backend (backend/app/config.py).
export const APP_VERSION = '1.1.0'
export const APP_CHANNEL = 'stable'
export const APP_BUILD = '20260926'   // fecha de este build — sirve para verificar que el binario es reciente
// Versión estable sin sufijo; los canales de prueba lo muestran (v1.2.0-beta).
export const APP_VERSION_LABEL = APP_CHANNEL === 'stable' ? `v${APP_VERSION}` : `v${APP_VERSION}-${APP_CHANNEL}`
