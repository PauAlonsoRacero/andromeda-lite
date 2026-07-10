/**
 * AlertsWidget.jsx — Configuración de alertas y notificaciones estilo Claude.
 * Notificaciones: respuesta terminada, VRAM baja, Ollama desconectado, errores.
 * Usa Notification API del navegador + alertas del backend.
 */
import { createSignal, onMount, onCleanup, For, Show } from 'solid-js'
import axios from 'axios'
import { hardware, health } from '../stores/hardware.js'
import { t } from '../stores/i18n.js'

// Preferencias de notificación (persistidas en memoria de sesión)
const PREFS_KEY = 'andromeda_alert_prefs'
const defaultPrefs = {
  onComplete:   true,   // cuando la IA termina de responder
  onVramLow:    true,   // VRAM por debajo del umbral
  onOllamaDown: true,   // Ollama se desconecta
  onError:      true,   // error en una respuesta
  browserNotif: false,  // notificaciones del sistema operativo
  sound:        false,  // sonido al completar
}

let _prefs = { ...defaultPrefs }
try {
  const saved = sessionStorage.getItem(PREFS_KEY)
  if (saved) _prefs = { ...defaultPrefs, ...JSON.parse(saved) }
} catch {}

export function getAlertPrefs() { return _prefs }
export function notifyComplete(latencyMs) {
  if (_prefs.onComplete && _prefs.browserNotif) {
    _showBrowserNotif('Respuesta completada', `Andromeda terminó en ${(latencyMs/1000).toFixed(1)}s`)
  }
  if (_prefs.onComplete && _prefs.sound) _playSound()
}
function _showBrowserNotif(title, body) {
  if (typeof Notification === 'undefined') return
  if (Notification.permission === 'granted') new Notification(title, { body })
}
function _playSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const osc = ctx.createOscillator(); const gain = ctx.createGain()
    osc.connect(gain); gain.connect(ctx.destination)
    osc.frequency.value = 880; gain.gain.value = 0.1
    osc.start(); osc.stop(ctx.currentTime + 0.15)
  } catch {}
}

export default function AlertsWidget() {
  const [prefs, setPrefs] = createSignal({ ..._prefs })
  const [alerts, setAlerts] = createSignal([])
  let interval

  function update(key, val) {
    const next = { ...prefs(), [key]: val }
    setPrefs(next)
    _prefs = next
    try { sessionStorage.setItem(PREFS_KEY, JSON.stringify(next)) } catch {}
    // Pedir permiso de notificaciones del navegador si se activa
    if (key === 'browserNotif' && val && typeof Notification !== 'undefined') {
      Notification.requestPermission()
    }
  }

  async function checkAlerts() {
    try {
      const r = await axios.get('/api/alerts')
      setAlerts(r.data.alerts || [])
    } catch {}
  }

  onMount(() => {
    checkAlerts()
    interval = setInterval(checkAlerts, 30_000)
  })
  onCleanup(() => clearInterval(interval))

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="font-size:22px;font-weight:700;margin-bottom:6px">{t('ui2.alerts_notif')}</div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:24px">{t('alert.subtitle')}</div>

      {/* Alertas activas ahora mismo */}
      <Show when={alerts().length > 0}>
        <div style="margin-bottom:24px">
          <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">{t('ui2.active_now')}</div>
          <For each={alerts()}>
            {(a) => (
              <div class="banner banner-warn" style="margin-bottom:8px">
                <span>{a.level === 'critical' ? '🔴' : a.level === 'warning' ? '🟡' : '🔵'}</span>
                <div style="font-size:13px">{a.message}</div>
              </div>
            )}
          </For>
        </div>
      </Show>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:8px 0 4px">{t('alert.events')}</div>
      <Row title={t('alert.resp_done')} desc={t('alert.resp_done_d')}>
        <Toggle checked={prefs().onComplete} onChange={v => update('onComplete', v)} />
      </Row>
      <Row title={t('alert.low_vram')} desc={t('alert.low_vram_d')}>
        <Toggle checked={prefs().onVramLow} onChange={v => update('onVramLow', v)} />
      </Row>
      <Row title={t('alert.ollama_disc')} desc={t('alert.ollama_disc_d')}>
        <Toggle checked={prefs().onOllamaDown} onChange={v => update('onOllamaDown', v)} />
      </Row>
      <Row title={t('alert.errors')} desc={t('alert.errors_d')}>
        <Toggle checked={prefs().onError} onChange={v => update('onError', v)} />
      </Row>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('alert.how')}</div>
      <Row title={t('alert.sys_notif')} desc={t('alert.sys_notif_d')}>
        <Toggle checked={prefs().browserNotif} onChange={v => update('browserNotif', v)} />
      </Row>
      <Row title={t('alert.sound')} desc={t('alert.sound_d')}>
        <Toggle checked={prefs().sound} onChange={v => update('sound', v)} />
      </Row>
    </div>
  )
}

function Row(props) {
  return (
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:16px 0;border-bottom:1px solid var(--glass-border)">
      <div style="flex:1">
        <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:3px">{props.title}</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.5">{props.desc}</div>
      </div>
      <div style="flex-shrink:0;padding-top:2px">{props.children}</div>
    </div>
  )
}

function Toggle(props) {
  return (
    <button
      onClick={() => props.onChange(!props.checked)}
      style={{
        width: '46px', height: '28px', 'border-radius': '14px', border: 'none',
        cursor: 'pointer', position: 'relative', transition: 'all 0.2s', 'flex-shrink': 0,
        background: props.checked ? 'var(--green)' : 'rgba(255,255,255,0.15)',
      }}
    >
      <span style={{
        position: 'absolute', top: '3px', left: props.checked ? '21px' : '3px',
        width: '22px', height: '22px', 'border-radius': '50%', background: 'white',
        transition: 'all 0.2s', 'box-shadow': '0 1px 3px rgba(0,0,0,0.3)',
      }} />
    </button>
  )
}
