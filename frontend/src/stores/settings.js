/**
 * settings.js — Ajustes de UI compartidos, reactivos y persistentes.
 * Un signal por ajuste: cualquier componente que lo importe se actualiza al instante.
 *
 * Persistencia: localStorage (rápido) + backend en disco (fiable). En el binario
 * de escritorio (pywebview/WKWebView) localStorage NO persiste entre arranques,
 * así que respaldamos cada ajuste en /api/uistate, que escribe en disco. Al
 * arrancar, hydrateFromBackend() relee esos valores y rehidrata los signals.
 */
import { createSignal } from 'solid-js'

// Registro de setters por clave, para poder rehidratar desde el backend.
const _setters = {}
let _hydrating = false   // evita reenviar al backend lo que viene del backend

function _saveToBackend(key, value) {
  if (_hydrating) return
  try {
    fetch(`/api/uistate/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    }).catch(() => {})
  } catch {}
}

function persisted(key, initial) {
  let v = initial
  try { v = JSON.parse(localStorage.getItem(key) ?? JSON.stringify(initial)) } catch { /* default */ }
  const [get, set] = createSignal(v)
  const setter = (nv) => {
    set(nv)
    try { localStorage.setItem(key, JSON.stringify(nv)) } catch { /* private mode */ }
    _saveToBackend(key, nv)
  }
  _setters[key] = (val) => { _hydrating = true; try { set(val) } finally { _hydrating = false } }
  return [get, setter]
}

/**
 * Rehidrata todos los ajustes desde el backend (disco). Llamar una vez al
 * arrancar la app. Sobrescribe los signals con lo guardado en disco, que en el
 * binario es la única fuente fiable.
 */
export async function hydrateFromBackend() {
  try {
    const r = await fetch('/api/uistate')
    if (!r.ok) return
    const { state } = await r.json()
    if (!state || typeof state !== 'object') return
    for (const [key, val] of Object.entries(state)) {
      if (_setters[key] && val !== undefined && val !== null) {
        _setters[key](val)
        try { localStorage.setItem(key, JSON.stringify(val)) } catch {}
      }
    }
  } catch { /* sin backend (modo web): localStorage basta */ }
}

// General
export const [advancedMode, setAdvancedMode]   = persisted('andromeda_advanced_mode', false)
export const [streamTokens, setStreamTokens]   = persisted('andromeda_stream', true)
export const [autoTitle, setAutoTitle]         = persisted('andromeda_auto_title', true)
export const [saveHistory, setSaveHistory]     = persisted('andromeda_save_history', true)
export const [showLatency, setShowLatency]     = persisted('andromeda_show_latency', true)
export const [showBadges, setShowBadges]       = persisted('andromeda_show_badges', true)
export const [compactMode, setCompactMode]     = persisted('andromeda_compact', false)
export const [defaultParallel, setDefaultParallel] = persisted('andromeda_default_parallel', 'auto')
export const [temperature, setTemperature]     = persisted('andromeda_temperature', 0.7)

// ── Capacidades (toggles funcionales que gatean comportamiento en el backend) ──
// Memoria
export const [memAutogenerate, setMemAutogenerate]       = persisted('andromeda_mem_autogenerate', true)
export const [memConversationSearch, setMemConversationSearch] = persisted('andromeda_mem_conversation_search', true)
// General
export const [connectorSearch, setConnectorSearch]       = persisted('andromeda_connector_search', false)
export const [modelFallback, setModelFallback]           = persisted('andromeda_model_fallback', true)
// Model Registry: servir el modelo promovido a producción
export const [serveProduction, setServeProduction]       = persisted('andromeda_serve_production', false)
// Visuales
export const [artifactsEnabled, setArtifactsEnabled]     = persisted('andromeda_artifacts_enabled', true)
export const [inlineViz, setInlineViz]                   = persisted('andromeda_inline_viz', true)
// Ejecución de archivos y red
export const [fileCreation, setFileCreation]             = persisted('andromeda_file_creation', true)
export const [networkEgress, setNetworkEgress]           = persisted('andromeda_network_egress', false)

// Tema: 'dark' | 'light'  (incógnito es un estado aparte, no un tema)
export const [theme, setTheme]                 = persisted('andromeda_theme', 'dark')

// Visuales
export const [orbsOn, setOrbsOn]               = persisted('andromeda_orbs', true)
// Estilo de fondo animado: 'orbs' | 'bands' | 'waves' (olas)
export const [bgStyle, setBgStyle]             = persisted('andromeda_bg_style', 'bands')
// Nº de colores en el fondo de olas (2, 3 o 4)
export const [waveCount, setWaveCount]         = persisted('andromeda_wave_count', 3)
// Altura de las olas en % de la altura de la app (30–70)
export const [waveHeight, setWaveHeight]       = persisted('andromeda_wave_height', 55)
export const [animationsOn, setAnimationsOn]   = persisted('andromeda_animations', true)
export const [syntaxHl, setSyntaxHl]           = persisted('andromeda_syntax_hl', true)
export const [lineNumbers, setLineNumbers]     = persisted('andromeda_line_numbers', true)

// Personalización de orbes de fondo
//   orbPalette: clave de un preset de paletas (ver presets body.orb-* en index.css)
//   orbSpeed:   multiplicador de velocidad (0.4 = lento … 2.0 = rápido). 1 = normal.
//   orbIntensity: opacidad/brillo global de los orbes (0.4 … 1.4)
export const [orbPalette, setOrbPalette]       = persisted('andromeda_orb_palette', 'aurora')
export const [orbSpeed, setOrbSpeed]           = persisted('andromeda_orb_speed', 1)
export const [orbIntensity, setOrbIntensity]   = persisted('andromeda_orb_intensity', 1)
export const [orbSize, setOrbSize]             = persisted('andromeda_orb_size', 1)        // 0.5 … 1.8
// Colores personalizados: 3 hex. Si está activo, anula el preset de paleta.
export const [orbCustom, setOrbCustom]         = persisted('andromeda_orb_custom', false)
export const [orbColors, setOrbColors]         = persisted('andromeda_orb_colors', ['#e8623f', '#4257e8', '#b54fc8'])
