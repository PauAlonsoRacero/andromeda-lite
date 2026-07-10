/**
 * TitleBar.jsx — Barra de título custom para la app de escritorio (frameless).
 * Solo se muestra dentro de pywebview. Es parte del DOM: hereda el tema
 * (incluido el modo incógnito) automáticamente.
 */
import { createSignal, onMount, Show } from 'solid-js'
import { t } from '../stores/i18n.js'

export default function TitleBar() {
  const [isDesktop, setIsDesktop] = createSignal(!!window.pywebview)

  onMount(() => {
    // pywebview inyecta su API un instante después de cargar
    if (!window.pywebview) {
      const t = setTimeout(() => setIsDesktop(!!window.pywebview), 600)
      window.addEventListener('pywebviewready', () => { setIsDesktop(true); clearTimeout(t) }, { once: true })
    }
  })

  const api = () => window.pywebview?.api
  const isMac = /Mac/i.test(navigator.platform || navigator.userAgent)

  // Las llamadas a pywebview devuelven Promises; si una se rechaza (excepción
  // en Python) y no la capturamos, algunas builds dejan de procesar clics
  // siguientes. Capturamos siempre.
  const call = (fn) => {
    try {
      const p = api()?.[fn]?.()
      if (p && typeof p.catch === 'function') p.catch(() => {})
    } catch { /* api no lista todavía */ }
  }

  return (
    <Show when={isDesktop()}>
      <div class="titlebar">
        <Show when={isMac}>
          <div class="titlebar-traffic">
            <button class="tl tl-close" title={t('title.close')} onClick={() => call('close')} />
            <button class="tl tl-min" title={t('title.minimize')} onClick={() => call('minimize')} />
            <button class="tl tl-max" title={t('title.maximize')} onClick={() => call('toggle_maximize')} />
          </div>
        </Show>
        <div class="titlebar-drag pywebview-drag-region">
          <img src="/andromeda-logo.png" alt="" style="width:16px;height:16px;object-fit:contain;opacity:0.8" />
          <span class="titlebar-name">Andromeda</span>
        </div>
        <Show when={!isMac}><div class="titlebar-controls">
          <button class="tb-btn" title={t('title.minimize')} onClick={() => call('minimize')}>
            <svg width="11" height="11" viewBox="0 0 11 11"><line x1="1" y1="5.5" x2="10" y2="5.5" stroke="currentColor" stroke-width="1.1"/></svg>
          </button>
          <button class="tb-btn" title={t('title.maximize')} onClick={() => call('toggle_maximize')}>
            <svg width="11" height="11" viewBox="0 0 11 11"><rect x="1.5" y="1.5" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.1"/></svg>
          </button>
          <button class="tb-btn tb-close" title={t('title.close')} onClick={() => call('close')}>
            <svg width="11" height="11" viewBox="0 0 11 11"><path d="M1.5 1.5 L9.5 9.5 M9.5 1.5 L1.5 9.5" stroke="currentColor" stroke-width="1.1"/></svg>
          </button>
        </div></Show>
      </div>
    </Show>
  )
}
