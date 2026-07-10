/**
 * hardware.js — Estado reactivo del hardware y salud del sistema.
 *
 * Polling inteligente:
 *   - Cada 30s cuando todo está OK
 *   - Cada 5s cuando hay error (reintento rápido)
 *   - Para cuando el tab está oculto (Page Visibility API)
 */

import { createSignal } from 'solid-js'
import axios from 'axios'

const [hardware, setHardware]               = createSignal(null)
const [liveUsage, setLiveUsage]             = createSignal(null)   // RAM/VRAM en tiempo real
const [policy, setPolicy]                   = createSignal(null)
const [health, setHealth]                   = createSignal(null)
const [activeSpecialists, setActiveSpecialists] = createSignal([])
const [loading, setLoading]                 = createSignal(true)
const [lastError, setLastError]             = createSignal(null)
const [lastRefresh, setLastRefresh]         = createSignal(null)

let _pollTimer = null
let _pollInterval = 30_000  // 30s normal, 5s on error

export async function refreshHardware() {
  try {
    const [hw, pol, hth, specs] = await Promise.allSettled([
      axios.get('/api/health/hardware').then(r => r.data),
      axios.get('/api/health/policy').then(r => r.data),
      axios.get('/api/health').then(r => r.data),
      axios.get('/api/models/active').then(r => r.data),
    ])

    if (hw.status === 'fulfilled')    setHardware(hw.value)
    if (pol.status === 'fulfilled')   setPolicy(pol.value)
    if (hth.status === 'fulfilled')   setHealth(hth.value)
    if (specs.status === 'fulfilled') setActiveSpecialists(specs.value.specialists || [])

    setLastError(null)
    setLastRefresh(new Date())
    _pollInterval = 30_000

  } catch (e) {
    setLastError(e.message)
    _pollInterval = 5_000  // retry faster on error
  } finally {
    setLoading(false)
    _schedulePoll()
  }
}

function _schedulePoll() {
  clearTimeout(_pollTimer)
  // Don't poll when tab is hidden
  if (document.visibilityState === 'hidden') return
  _pollTimer = setTimeout(refreshHardware, _pollInterval)
}

// Pause/resume polling with tab visibility
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      refreshHardware()  // immediate refresh when tab becomes visible
    } else {
      clearTimeout(_pollTimer)
    }
  })
}

// Initial load
if (typeof window !== 'undefined') {
  refreshHardware()
}

// ── Uso en vivo (RAM/VRAM): sondeo rápido (4s) e independiente del estático ──
let _liveTimer = null
export async function refreshLiveUsage() {
  try {
    const u = await axios.get('/api/health/hardware/live').then(r => r.data)
    setLiveUsage(u)
  } catch { /* best-effort */ }
  clearTimeout(_liveTimer)
  if (document.visibilityState !== 'hidden') {
    _liveTimer = setTimeout(refreshLiveUsage, 4_000)
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshLiveUsage()
    else clearTimeout(_liveTimer)
  })
}
if (typeof window !== 'undefined') {
  refreshLiveUsage()
}

export { hardware, liveUsage, policy, health, activeSpecialists, loading, lastError, lastRefresh }
