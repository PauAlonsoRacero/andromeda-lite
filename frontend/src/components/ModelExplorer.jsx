/**
 * ModelExplorer.jsx — Biblioteca de IAs con estética iOS 26.
 * Busca modelos, mira si caben en TU hardware, descárgalos.
 * Lo central: "¿cabe en mi GPU ahora mismo?" (asumiendo que solo se usa esa IA).
 */
import { createSignal, onMount, onCleanup, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

const TIER_COLOR = { 1: 'var(--green)', 2: 'var(--blue)', 3: 'var(--purple)', 4: 'var(--pink)' }
const TIER_LABEL = { 1: 'T1', 2: 'T2', 3: 'T3', 4: 'T4' }

export default function ModelExplorer() {
  const [catalog, setCatalog] = createSignal([])
  const [query, setQuery]     = createSignal('')
  const [loading, setLoading] = createSignal(true)
  const [pulling, setPulling] = createSignal({})
  const [progress, setProgress] = createSignal({})   // {model: {pct, status, done_mb, total_mb}}
  const [hw, setHw]           = createSignal({ detected: false })
  const [tierFilter, setTierFilter] = createSignal(null)     // null | 1..4
  const [vramFilter, setVramFilter] = createSignal(null)     // null | 8 | 16 | 24 | 48
  const [fitsOnly, setFitsOnly]     = createSignal(false)    // solo los que caben
  const pollers = {}

  // Catálogo filtrado en cliente por tier / VRAM máxima / "solo los que caben"
  const filtered = () => catalog().filter(m => {
    if (tierFilter() && m.tier !== tierFilter()) return false
    if (vramFilter() && (m.vram_estimated_gb || 0) > vramFilter()) return false
    if (fitsOnly() && m.fits_status === 'no_apto') return false
    return true
  })

  onMount(load)
  onCleanup(() => Object.values(pollers).forEach(clearInterval))

  async function load() {
    setLoading(true)
    try {
      const r = await axios.get('/api/models/catalog', { params: { q: query() } })
      setCatalog(r.data.models || [])
      setHw({ detected: r.data.hardware_detected, vram: r.data.user_vram_gb, bandwidth: r.data.user_bandwidth_gbs })
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  async function pull(name) {
    setPulling(p => ({ ...p, [name]: 'descargando' }))
    setProgress(p => ({ ...p, [name]: { pct: 0, status: 'iniciando', done_mb: 0, total_mb: 0 } }))
    try {
      await axios.post('/api/models/pull', { model_name: name })
      // Polling del progreso cada segundo
      pollers[name] = setInterval(async () => {
        try {
          const r = await axios.get(`/api/models/pull-progress/${encodeURIComponent(name)}`)
          const j = r.data
          setProgress(p => ({ ...p, [name]: j }))
          if (j.pct >= 100) {
            clearInterval(pollers[name]); delete pollers[name]
            setPulling(p => ({ ...p, [name]: 'completado' }))
          } else if (j.pct === -1) {
            clearInterval(pollers[name]); delete pollers[name]
            setPulling(p => ({ ...p, [name]: 'error' }))
          }
        } catch { /* backend offline momentáneo: seguir intentando */ }
      }, 1000)
    } catch (e) { setPulling(p => ({ ...p, [name]: 'error' })) }
  }

  async function bakeIdentity(name) {
    setPulling(p => ({ ...p, [name]: 'grabando' }))
    try {
      const r = await axios.post('/api/models/bake-identity', { model_name: name })
      setPulling(p => ({ ...p, [name]: 'grabada:' + r.data.variant }))
    } catch (e) { setPulling(p => ({ ...p, [name]: 'error' })) }
  }

  let searchTimer
  function onSearch(v) {
    setQuery(v)
    clearTimeout(searchTimer)
    searchTimer = setTimeout(load, 300)
  }

  return (
    <div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:16px;line-height:1.5">
        {t('mex.intro')}
      </div>

      {/* Hardware detectado — chip iOS */}
      <Show when={hw().detected} fallback={
        <div class="ios-chip" style="margin-bottom:18px;color:var(--text-3)">
          <span style="width:7px;height:7px;border-radius:50%;background:var(--text-3)"></span>
          {t('mex.no_gpu')}
        </div>
      }>
        <div class="ios-chip anim-spring" style="margin-bottom:18px">
          <span class="anim-pulse" style="width:7px;height:7px;border-radius:50%;background:var(--green)"></span>
          <span style="color:var(--text-2)"><b style="color:var(--text-1)">{hw().vram} GB</b> {t('mex.vram_detected')}</span>
          <Show when={hw().bandwidth > 0}>
            <span style="color:var(--text-3)">· {hw().bandwidth} GB/s</span>
          </Show>
        </div>
      </Show>

      {/* Buscador iOS */}
      <div class="ios-search" style="margin-bottom:14px">
        <span style="color:var(--text-3);font-size:15px">⌕</span>
        <input placeholder={t('mex.ph_search')} value={query()}
          onInput={e => onSearch(e.target.value)} />
      </div>

      {/* Filtros: categoría (tier) y espacio (VRAM) */}
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:20px">
        <span style="font-size:11px;color:var(--text-3);font-weight:600;margin-right:2px">{t('mex.category')}</span>
        <For each={[1,2,3,4]}>
          {(tn) => (
            <button onClick={() => setTierFilter(tierFilter()===tn ? null : tn)}
              style={`font-size:11px;font-weight:600;padding:5px 11px;border-radius:9px;cursor:pointer;font-family:var(--font);transition:all .14s;
                border:1px solid ${tierFilter()===tn ? TIER_COLOR[tn] : 'var(--glass-border)'};
                background:${tierFilter()===tn ? TIER_COLOR[tn]+'22' : 'var(--hover-surface)'};
                color:${tierFilter()===tn ? TIER_COLOR[tn] : 'var(--text-2)'}`}>
              {TIER_LABEL[tn]}
            </button>
          )}
        </For>
        <span style="width:1px;height:18px;background:var(--glass-border);margin:0 4px" />
        <span style="font-size:11px;color:var(--text-3);font-weight:600;margin-right:2px">{t('mex.max_space')}</span>
        <For each={[8,16,24,48]}>
          {(gb) => (
            <button onClick={() => setVramFilter(vramFilter()===gb ? null : gb)}
              style={`font-size:11px;font-weight:600;padding:5px 11px;border-radius:9px;cursor:pointer;font-family:var(--font);transition:all .14s;
                border:1px solid ${vramFilter()===gb ? 'var(--blue)' : 'var(--glass-border)'};
                background:${vramFilter()===gb ? 'var(--blue)22' : 'var(--hover-surface)'};
                color:${vramFilter()===gb ? 'var(--blue)' : 'var(--text-2)'}`}>
              ≤{gb} GB
            </button>
          )}
        </For>
        <span style="width:1px;height:18px;background:var(--glass-border);margin:0 4px" />
        <button onClick={() => setFitsOnly(!fitsOnly())}
          style={`font-size:11px;font-weight:600;padding:5px 11px;border-radius:9px;cursor:pointer;font-family:var(--font);transition:all .14s;
            border:1px solid ${fitsOnly() ? 'var(--green)' : 'var(--glass-border)'};
            background:${fitsOnly() ? 'var(--green)22' : 'var(--hover-surface)'};
            color:${fitsOnly() ? 'var(--green)' : 'var(--text-2)'}`}>
          {t('mex.fits_only')}
        </button>
        <Show when={tierFilter() || vramFilter() || fitsOnly()}>
          <button onClick={() => { setTierFilter(null); setVramFilter(null); setFitsOnly(false) }}
            style="font-size:11px;color:var(--text-3);background:none;border:none;cursor:pointer;text-decoration:underline">
            Limpiar
          </button>
        </Show>
      </div>

      <Show when={!loading()} fallback={
        <div style="text-align:center;padding:40px;color:var(--text-3)">{t('mex.loading')}</div>
      }>
        <Show when={filtered().length > 0} fallback={
          <div style="text-align:center;padding:40px;color:var(--text-3);font-size:13px">{t('mex.no_match')}</div>
        }>
        <div class="stagger" style="display:flex;flex-direction:column;gap:14px">
          <For each={filtered()}>
            {(m) => (
              <div class="ios-model-card lift">
                {/* Cabecera: nombre + tier + estado */}
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
                  <div style="flex:1;min-width:0">
                    <div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap">
                      <span style="font-size:16px;font-weight:700;font-family:var(--font-mono);letter-spacing:-0.01em">{m.name}</span>
                      <span class="ios-tier-badge" style={`color:${TIER_COLOR[m.tier]};border-color:${TIER_COLOR[m.tier]}33`}>
                        {TIER_LABEL[m.tier]}
                      </span>
                      <Show when={m.supports_tools}>
                        <span class="ios-tier-badge" title={t('mex.tools_hint')}
                          style="color:var(--green);border-color:var(--green)33">🔧 {t('mex.tools')}</span>
                      </Show>
                    </div>
                    <div style="font-size:12px;color:var(--text-3);margin-top:4px">{m.family} · {m.params_b}B · {(m.context/1024).toFixed(0)}k {t('mex.context')}</div>
                  </div>

                  {/* Estado "apto" — lo más prominente */}
                  <Show when={m.fits_status !== undefined}>
                    <div class="ios-fit-pill" style={
                      m.fits_status === 'apto'       ? 'background:rgba(52,211,153,0.14);color:var(--green)' :
                      m.fits_status === 'apto_justo' ? 'background:rgba(240,164,140,0.16);color:var(--pink)' :
                                                       'background:rgba(255,107,107,0.14);color:var(--red)'}>
                      <span style="font-size:13px">{m.fits_status === 'no_apto' ? '✕' : '✓'}</span>
                      {m.fits_status === 'apto' ? t('mex.fit_apto') : m.fits_status === 'apto_justo' ? t('mex.fit_justo') : t('mex.fit_no')}
                    </div>
                  </Show>
                </div>

                {/* Descripción */}
                <div style="font-size:13px;color:var(--text-2);line-height:1.55;margin:12px 0">{m.description}</div>

                {/* Métricas en píldoras iOS */}
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
                  <div class="ios-metric">
                    <span class="ios-metric-label">VRAM</span>
                    <span class="ios-metric-value">{m.vram_estimated_gb} GB</span>
                  </div>
                  <Show when={m.est_tokens_per_sec !== undefined}>
                    <div class="ios-metric">
                      <span class="ios-metric-label">{t('mex.speed')}</span>
                      <span class="ios-metric-value">~{m.est_tokens_per_sec} tok/s</span>
                    </div>
                  </Show>
                  <Show when={m.speed_label}>
                    <div class="ios-metric">
                      <span class="ios-metric-label">Fluidez</span>
                      <span class="ios-metric-value" style={`color:${m.speed_label==='Muy rápido'?'var(--green)':m.speed_label==='Rápido'?'var(--blue)':m.speed_label==='Usable'?'var(--purple)':'var(--text-2)'}`}>{t('mex.spd_'+({'Muy rápido':'muyrapido','Rápido':'rapido','Usable':'usable','Lento':'lento'}[m.speed_label]||'usable'))}</span>
                    </div>
                  </Show>
                  <Show when={m.vram_headroom_gb !== undefined && m.fits_status !== 'no_apto'}>
                    <div class="ios-metric">
                      <span class="ios-metric-label">{t('ui2.free_margin')}</span>
                      <span class="ios-metric-value">{m.vram_headroom_gb} GB</span>
                    </div>
                  </Show>
                </div>

                {/* Usos */}
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px">
                  <For each={m.uses}>
                    {(u) => <span class="ios-tag">{(() => { const k='use.'+u; const v=t(k); return v===k?u:v })()}</span>}
                  </For>
                </div>

                {/* Acciones */}
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                  <button class="btn btn-primary" style="font-size:13px;padding:9px 18px"
                    disabled={pulling()[m.name] === 'descargando'}
                    onClick={() => pull(m.name)}>
                    <Show when={pulling()[m.name] === 'descargando'} fallback={
                      <Show when={pulling()[m.name] === 'completado'} fallback={t('mex.download')}>{t('mex.redownload')}</Show>
                    }>{t('mex.downloading')}</Show>
                  </button>
                  <button class="btn btn-glass" style="font-size:13px;padding:9px 16px"
                    disabled={pulling()[m.name] === 'grabando'}
                    onClick={() => bakeIdentity(m.name)}
                    title={t('mex.variant_hint')}>
                    <Show when={pulling()[m.name] === 'grabando'} fallback={t('mex.record_id')}>{t('mex.recording')}</Show>
                  </button>
                </div>

                {/* Barra de progreso de descarga */}
                <Show when={pulling()[m.name] === 'descargando'}>
                  <div class="dl-progress anim-slide">
                    <div class="dl-progress-head">
                      <span class="dl-progress-status">{progress()[m.name]?.status || 'preparando'}</span>
                      <span class="dl-progress-nums">
                        <Show when={(progress()[m.name]?.total_mb || 0) > 0}>
                          {((progress()[m.name]?.done_mb || 0) / 1024).toFixed(1)} / {((progress()[m.name]?.total_mb || 0) / 1024).toFixed(1)} GB ·{' '}
                        </Show>
                        {(progress()[m.name]?.pct || 0).toFixed(0)}%
                      </span>
                    </div>
                    <div class="dl-progress-track">
                      <div class="dl-progress-fill" style={`width:${Math.max(2, progress()[m.name]?.pct || 0)}%`} />
                    </div>
                  </div>
                </Show>

                {/* Confirmaciones */}
                <Show when={pulling()[m.name] === 'completado'}>
                  <div class="ios-note ios-note-ok">✓ <b style="font-family:var(--font-mono)">{m.name}</b> {t('mex.dl_ok')}</div>
                </Show>
                <Show when={(pulling()[m.name] || '').startsWith('grabada:')}>
                  <div class="ios-note ios-note-ok">{t('ui2.variant_created')}<b style="font-family:var(--font-mono)">{(pulling()[m.name] || '').replace('grabada:', '')}</b>{t('mex.assign')}</div>
                </Show>
                <Show when={pulling()[m.name] === 'error'}>
                  <div class="ios-note ios-note-err">{t('mex.dl_fail')}</div>
                </Show>
              </div>
            )}
          </For>
          <Show when={catalog().length === 0}>
            <div style="text-align:center;padding:40px;color:var(--text-3)">Sin resultados para "{query()}"</div>
          </Show>
        </div>
        </Show>
      </Show>
    </div>
  )
}
