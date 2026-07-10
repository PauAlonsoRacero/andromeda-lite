/**
 * edition.js — Edición activa de Andromeda (Lite / Pro) y feature gating en UI.
 *
 * Consulta /api/edition al arrancar. Expone:
 *   edition()      → 'lite' | 'pro'
 *   isPro()        → boolean
 *   hasFeature(k)  → boolean   (¿la feature está en la edición activa?)
 *   editionLabel() → 'Andromeda Lite' | 'Andromeda Pro'
 *
 * Mientras carga, asume Lite (la opción más restrictiva): nunca mostramos como
 * disponible algo que luego resulte capado.
 */
import { createSignal } from 'solid-js'
import axios from 'axios'

const [edition, setEdition]       = createSignal('lite')
const [features, setFeatures]     = createSignal({})
const [label, setLabel]           = createSignal('Andromeda Lite')
const [loaded, setLoaded]         = createSignal(false)
const [licenseHolder, setHolder]  = createSignal(null)

export async function loadEdition() {
  try {
    const r = await axios.get('/api/edition')
    setEdition(r.data.edition || 'lite')
    setFeatures(r.data.features || {})
    setLabel(r.data.label || 'Andromeda Lite')
    setHolder(r.data.license_holder || null)
  } catch {
    // Sin backend de edición → Lite por defecto
    setEdition('lite'); setFeatures({}); setLabel('Andromeda Lite')
  } finally {
    setLoaded(true)
  }
}

export const editionName  = edition
export const editionLabel = label
export const isPro         = () => edition() === 'pro'
export const editionLoaded = loaded
export const editionHolder = licenseHolder
export const hasFeature    = (key) => !!features()[key]

// ── Gating del panel Analytics ──────────────────────────────────────────────
// Decisión de negocio (Pau): la observabilidad BÁSICA (memorias, herramientas,
// latencia) está en Lite porque es parte del "plug-and-play funciona". La
// observabilidad avanzada MLOps (drift, proyecciones, series, comparativas)
// sigue siendo Pro en StatsPanel.
//
// Si quieres que hasta lo básico sea solo Pro, cambia esta línea a:
//   export const analyticsAvailable = () => isPro()
export const analyticsAvailable = () => true
