/**
 * auth.js — Sesión del usuario. Token en localStorage + cabecera global axios.
 * Soporta "recordarme": la sesión persiste un máximo de REMEMBER_DAYS días
 * (igual que el horizonte largo de sesión de Claude). Sin "recordarme", la
 * sesión solo vive mientras la pestaña/app esté abierta (sessionStorage).
 */
import { createSignal } from 'solid-js'
import axios from 'axios'

const REMEMBER_DAYS = 30   // mismo horizonte que mantiene Claude las sesiones largas
const SESSION_KEY = 'andromeda_session'

function loadSaved() {
  try {
    // Primero la persistente (recordarme); si no, la de sesión (solo esta apertura)
    const raw = localStorage.getItem(SESSION_KEY) || sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const s = JSON.parse(raw)
    // Caducidad de "recordarme"
    if (s?.expires_at && Date.now() > s.expires_at) {
      localStorage.removeItem(SESSION_KEY); sessionStorage.removeItem(SESSION_KEY)
      return null
    }
    return s
  } catch { return null }
}

const saved = loadSaved()

export const [session, setSessionRaw] = createSignal(saved)        // {token, username, plan, remember, expires_at} | null
export const [authRequired, setAuthRequired] = createSignal(false)
export const [authChecked, setAuthChecked] = createSignal(false)
// El usuario abre el login manualmente desde Configuración (en Lite la sesión
// es opcional: solo sirve para conectar con la nube y desbloquear Pro).
export const [showLogin, setShowLogin] = createSignal(false)

function applyHeader(s) {
  if (s?.token) axios.defaults.headers.common['X-Andromeda-Token'] = s.token
  else delete axios.defaults.headers.common['X-Andromeda-Token']
}
applyHeader(saved)

export function setSession(s, remember = null) {
  // remember: true → persiste 30 días; false → solo esta sesión; null → conserva el modo previo
  if (s) {
    const rem = remember === null ? (s.remember ?? true) : remember
    s = { ...s, remember: rem }
    if (rem) s.expires_at = Date.now() + REMEMBER_DAYS * 86400_000
  }
  setSessionRaw(s)
  applyHeader(s)
  try {
    localStorage.removeItem(SESSION_KEY)
    sessionStorage.removeItem(SESSION_KEY)
    if (s) {
      const store = s.remember ? localStorage : sessionStorage
      store.setItem(SESSION_KEY, JSON.stringify(s))
    }
  } catch { /* private mode */ }
}

export async function checkAuth() {
  // En Lite la cuenta es OPCIONAL: Andromeda funciona 100% local sin sesión,
  // así que NUNCA forzamos la pantalla de login al arrancar. El login solo
  // aparece si el usuario lo abre a mano desde Configuración (showLogin).
  // Aquí únicamente intentamos refrescar una sesión ya existente (para
  // mantener el plan al día), sin bloquear nada si no hay sesión o no hay red.
  setAuthRequired(false)
  if (session()) {
    try {
      const r = await axios.post('/api/cloud/refresh')
      if (r.data.user) {
        const s = session()
        const u = r.data.user
        if (s) setSession({ ...s, username: u.display_name || u.email, email: u.email, plan: r.data.plan })
      } else {
        // El cloud confirma que la sesión ya no vale → la limpiamos, pero
        // NO forzamos login: el usuario sigue usando Lite con normalidad.
        setSession(null)
      }
    } catch {
      // Sin respuesta (offline o sin servidor cloud): no tocamos la sesión
      // local. Con licencia válida, Pro sigue funcionando offline.
    }
  }
  setAuthChecked(true)
}

export async function logout() {
  try { await axios.post('/api/cloud/logout') } catch { /* ya caducada */ }
  setSession(null)
}

// Si cualquier petición devuelve 401 con auth_required → volver al login
axios.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401 && err.response?.data?.auth_required) setSession(null)
    return Promise.reject(err)
  }
)
