/**
 * PowerPack.jsx — Un modelo por nivel de potencia, según el equipo.
 *
 * La potencia automática elige entre los modelos instalados. Sin un modelo en
 * cada nivel, no tiene de dónde escoger. Esta tarjeta recomienda un pack según
 * la memoria del equipo y descarga lo que falta, de uno en uno (en paralelo
 * saturaría la conexión y el disco).
 */
import { createSignal, createResource, For, Show, onCleanup } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

export default function PowerPack() {
  const [pack, { refetch }] = createResource(async () => (await axios.get('/api/models/power-pack')).data)
  const [progreso, setProgreso] = createSignal({})      // modelo → { pct, estado }
  const [activo, setActivo] = createSignal(false)
  let cancelado = false
  onCleanup(() => { cancelado = true })

  const esperar = (ms) => new Promise(r => setTimeout(r, ms))

  async function descargar(modelo) {
    setProgreso(p => ({ ...p, [modelo]: { pct: 0, estado: 'downloading' } }))
    await axios.post('/api/models/pull', { model_name: modelo })
    while (!cancelado) {
      await esperar(1000)
      try {
        const j = (await axios.get(`/api/models/pull-progress/${encodeURIComponent(modelo)}`)).data
        if (j.pct === -1) { setProgreso(p => ({ ...p, [modelo]: { pct: 0, estado: 'error' } })); return false }
        setProgreso(p => ({ ...p, [modelo]: { pct: Math.max(0, j.pct || 0), estado: 'downloading' } }))
        if (j.pct >= 100) { setProgreso(p => ({ ...p, [modelo]: { pct: 100, estado: 'done' } })); return true }
      } catch { /* backend ocupado un instante: seguir */ }
    }
    return false
  }

  async function descargarFaltantes() {
    setActivo(true)
    for (const n of (pack()?.levels || []).filter(x => !x.installed)) {
      if (cancelado) break
      await descargar(n.model)
    }
    setActivo(false)
    refetch()
  }

  const faltan = () => (pack()?.levels || []).filter(x => !x.installed)

  return (
    <Show when={pack()}>
      <div class="card power-pack">
        <div class="power-pack-head">
          <div>
            <div class="power-pack-title">{t('pp.title')}</div>
            <div class="power-pack-sub">
              {t('pp.sub').replace('{gb}', pack().memory_gb)}
            </div>
          </div>
          <Show when={faltan().length} fallback={<span class="power-pack-ok">✓ {t('pp.complete')}</span>}>
            <button class="btn btn-primary" disabled={activo()} onClick={descargarFaltantes}>
              {activo() ? t('pp.downloading') : t('pp.download').replace('{gb}', pack().missing_download_gb)}
            </button>
          </Show>
        </div>
        <div class="power-pack-levels">
          <For each={pack().levels}>
            {(n) => {
              const pr = () => progreso()[n.model]
              return (
                <div class="power-pack-level" classList={{ installed: n.installed || pr()?.estado === 'done' }}>
                  <span class="power-pack-lvl">{t('cs.lvl_' + n.level)}</span>
                  <span class="power-pack-model">{n.model}</span>
                  <span class="power-pack-state">
                    <Show when={n.installed || pr()?.estado === 'done'} fallback={
                      <Show when={pr()?.estado === 'downloading'} fallback={
                        <Show when={pr()?.estado === 'error'} fallback={<>{n.download_gb} GB</>}>
                          {t('pp.error')}
                        </Show>
                      }>
                        <span class="power-pack-bar"><span style={{ width: `${pr().pct}%` }} /></span> {pr().pct}%
                      </Show>
                    }>✓</Show>
                  </span>
                </div>
              )
            }}
          </For>
        </div>
      </div>
    </Show>
  )
}
