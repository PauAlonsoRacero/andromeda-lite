/**
 * ComponentsHealth — estado de cada subsistema de Andromeda.
 *
 * Complementa a las analíticas de peticiones: en vez de "cómo van las
 * respuestas", responde "qué piezas están vivas y qué hacen".
 *
 * Al pulsar una tarjeta esta se expande en el sitio y el resto se reacomoda,
 * en lugar de abrir un modal que tape el contexto: así no se pierde de vista
 * la relación entre componentes.
 */
import { createResource, createSignal, For, Show, onCleanup } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import InfoButton from './InfoButton.jsx'
import { on, SYSTEM_CHANGED } from '../stores/events.js'

const META = {
  ollama:      { icon: '🧠', key: 'ollama' },
  specialists: { icon: '🎭', key: 'specialists' },
  memory:      { icon: '💭', key: 'memory' },
  rag:         { icon: '📚', key: 'rag' },
  skills:      { icon: '⚡', key: 'skills' },
  mcp:         { icon: '🔌', key: 'mcp' },
  web_search:  { icon: '🌐', key: 'web' },
  registry:    { icon: '📦', key: 'registry' },
  ab_testing:  { icon: '🔬', key: 'ab' },
  feedback:    { icon: '👍', key: 'feedback' },
  workspace:   { icon: '📁', key: 'workspace' },
}

/** Traduce el detalle que envía el backend, sustituyendo sus parámetros. */
function detail(c) {
  if (!c.detail_key) return c.detail || ''
  let txt = t(c.detail_key)
  for (const [k, v] of Object.entries(c.detail_args || {})) {
    txt = txt.replace(`{${k}}`, v)
  }
  return txt
}

export default function ComponentsHealth() {
  const [data, { refetch }] = createResource(async () =>
    (await axios.get('/api/components')).data)
  const [expanded, setExpandedRaw] = createSignal(null)
  let grid

  // Animación FLIP: se mide cada tarjeta, se aplica el cambio y se anima desde
  // la posición anterior. La tarjeta abierta crece hasta ocupar la fila y las
  // demás se deslizan a su sitio (antes todo saltaba sin transición).
  const setExpanded = (valor) => {
    const tarjetas = grid ? [...grid.children] : []
    const antes = new Map(tarjetas.map(el => [el, el.getBoundingClientRect()]))
    setExpandedRaw(valor)
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    requestAnimationFrame(() => {
      for (const el of tarjetas) {
        const a = antes.get(el), d = el.getBoundingClientRect()
        if (!a || !d.width || !d.height) continue
        const dx = a.left - d.left, dy = a.top - d.top
        const sx = a.width / d.width, sy = a.height / d.height
        if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < .01 && Math.abs(sy - 1) < .01) continue
        // Muelle suave al estilo de Apple: algo más largo y con un leve rebote.
        el.animate([
          { transformOrigin: 'top left', transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
          { transformOrigin: 'top left', transform: 'none' },
        ], { duration: 620, easing: 'cubic-bezier(.22, 1.18, .36, 1)' })
      }
      // Centrar el scroll en el cuadro abierto cuando termina de colocarse.
      if (valor) {
        const abierto = grid?.querySelector('.ch-card-open')
        if (abierto) setTimeout(() => abierto.scrollIntoView({ behavior: 'smooth', block: 'center' }), 140)
      }
    })
  }

  // Releer en cuanto el usuario cambie algo en otro panel.
  onCleanup(on(SYSTEM_CHANGED, () => refetch()))

  // Escape cierra la tarjeta abierta, como cualquier elemento expandido.
  const onKey = (e) => { if (e.key === 'Escape') setExpanded(null) }
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onKey)
    onCleanup(() => window.removeEventListener('keydown', onKey))
  }

  return (
    <div class="card" style="padding:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <div style="display:flex;align-items:center;gap:var(--sp-2)">
          <h3 class="section-title">{t('ch.title')}</h3>
          <InfoButton
            title={t('ch.title')}
            intro={t('ch.info_intro')}
            items={[
              { h: t('ch.st_ok'), d: t('ch.st_ok_d') },
              { h: t('ch.st_degraded'), d: t('ch.st_degraded_d') },
              { h: t('ch.st_off'), d: t('ch.st_off_d') },
              { h: t('ch.st_error'), d: t('ch.st_error_d') },
            ]}
          />
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <Show when={data()}>
            <span style="font-size:var(--fs-xs);color:var(--text-3)">
              {data().healthy}/{data().total} {t('ch.active')}
            </span>
          </Show>
          <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:3px 10px"
                  onClick={() => refetch()}>{t('ch.refresh')}</button>
        </div>
      </div>
      <p class="section-sub">{t('ch.desc')}</p>

      <Show when={data()} fallback={
        <div class="ch-grid">
          <For each={Array(8)}>{() => <div class="skeleton" style="height:112px;border-radius:18px" />}</For>
        </div>
      }>
        {/* Capa de cierre al pulsar fuera de la tarjeta expandida. */}
        <Show when={expanded()}>
          <div onClick={() => setExpanded(null)}
               style="position:fixed;inset:0;z-index:1" />
        </Show>

        <div class="ch-grid" ref={grid} classList={{ 'ch-grid-has-open': !!expanded() }}>
          <For each={Object.entries(data().components)}>
            {([id, c]) => {
              const isOpen = () => expanded() === id
              return (
                <div class="ch-card"
                     data-status={c.status}
                     classList={{ 'ch-card-open': isOpen(), 'ch-card-dim': !!expanded() && !isOpen() }}
                     onClick={(e) => { e.stopPropagation(); setExpanded(isOpen() ? null : id) }}
                     role="button" tabIndex={0}
                     onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(isOpen() ? null : id) } }}>
                  <div class="ch-card-glow" />

                  <div class="ch-card-top">
                    <span class="ch-icon-wrap"><span class="ch-icon">{META[id]?.icon || '•'}</span></span>
                    <div style="display:flex;align-items:center;gap:6px">
                      <span class="ch-status-pill" data-status={c.status}>
                        <span class="ch-dot" />
                        {t('ch.s_' + c.status)}
                      </span>
                      <Show when={isOpen()}>
                        <button class="ch-close" aria-label="close"
                                onClick={(e) => { e.stopPropagation(); setExpanded(null) }}>×</button>
                      </Show>
                    </div>
                  </div>

                  <div class="ch-name">{t('ch.n_' + (META[id]?.key || id))}</div>
                  <div class="ch-metric">{c.metric_key ? t(c.metric_key).replace('{n}', c.metric_n ?? '') : c.metric}</div>
                  <div class="ch-detail" classList={{ 'ch-detail-full': isOpen() }}>{detail(c)}</div>

                  {/* Contenido ampliado: qué es el componente y qué hacer ahora. */}
                  <Show when={isOpen()}>
                    <div class="ch-expand">
                      <div class="ch-expand-block">
                        <div class="ch-expand-h">{t('ch.what_is')}</div>
                        <div class="ch-expand-d">{t('ch.about_' + (META[id]?.key || id))}</div>
                      </div>
                      <div class="ch-expand-block">
                        <div class="ch-expand-h">{t('ch.next_step')}</div>
                        <div class="ch-expand-d">
                          {c.status === 'ok' ? t('ch.next_ok') : t('ch.hint_' + (META[id]?.key || id))}
                        </div>
                      </div>
                    </div>
                  </Show>
                </div>
              )
            }}
          </For>
        </div>
      </Show>
    </div>
  )
}
