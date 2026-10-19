/**
 * InfoButton.jsx — Botón (i) con explicación contextual.
 *
 * Popover anclado al botón, no un modal centrado: la explicación aparece junto
 * a lo que explica, así no se pierde la referencia visual de qué se describe.
 * Se posiciona solo para no salirse de la pantalla y se cierra con clic fuera,
 * Escape o el botón.
 */
import { createSignal, For, Show, onCleanup } from 'solid-js'
import { t } from '../stores/i18n.js'

export default function InfoButton(props) {
  const [open, setOpen] = createSignal(false)
  const [pos, setPos] = createSignal({ top: 0, left: 0, arrow: 0, above: false, width: 340 })
  let btnRef

  /** Sitúa el popover bajo el botón, corrigiendo si se saldría de la ventana. */
  function place() {
    if (!btnRef) return
    const r = btnRef.getBoundingClientRect()
    const W = Math.min(360, window.innerWidth - 24)
    const H = 320                            // alto estimado, para elegir arriba/abajo
    const above = r.bottom + H > window.innerHeight && r.top > H
    let left = r.left + r.width / 2 - W / 2
    left = Math.max(12, Math.min(left, window.innerWidth - W - 12))
    setPos({
      top: above ? r.top - 10 : r.bottom + 10,
      left,
      arrow: r.left + r.width / 2 - left,     // flecha alineada con el botón
      above,
      width: W,
    })
  }

  function toggle(e) {
    e?.stopPropagation()
    if (!open()) place()
    setOpen(v => !v)
  }
  const close = () => setOpen(false)

  if (typeof window !== 'undefined') {
    const onKey = (e) => { if (e.key === 'Escape') close() }
    const onMove = () => { if (open()) close() }
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onMove)
    window.addEventListener('scroll', onMove, true)
    onCleanup(() => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onMove)
      window.removeEventListener('scroll', onMove, true)
    })
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={toggle}
        title={props.label || t('info.how_it_works')}
        aria-label="info"
        aria-expanded={open()}
        class="info-dot"
        style={`background:${open() ? 'var(--glass-bright)' : 'transparent'};color:${open() ? 'var(--text-1)' : 'var(--text-3)'};border-color:${open() ? 'var(--text-3)' : 'var(--glass-border)'}`}
      >i</button>

      <Show when={open()}>
        {/* Captura de clics fuera. Transparente a propósito: el popover no
            oscurece la app, para poder seguir viendo lo que se explica. */}
        <div onClick={close} style="position:fixed;inset:0;z-index:300" />

        <div
          class={`info-pop ${pos().above ? 'info-pop-above' : ''}`}
          style={`top:${pos().top}px;left:${pos().left}px;width:${pos().width}px`}
        >
          <span class="info-pop-arrow" style={`left:${pos().arrow}px`} />

          <div class="info-pop-head">
            <h4>{props.title}</h4>
            <button onClick={close} aria-label="close">×</button>
          </div>

          <Show when={props.intro}>
            <p class="info-pop-intro">{props.intro}</p>
          </Show>

          <div class="info-pop-body">
            <For each={props.items || []}>
              {(it, i) => (
                <div class="info-pop-item" style={`animation-delay:${i() * 40}ms`}>
                  <div class="info-pop-item-h">{it.h}</div>
                  <div class="info-pop-item-d">{it.d}</div>
                </div>
              )}
            </For>
          </div>
        </div>
      </Show>
    </>
  )
}
