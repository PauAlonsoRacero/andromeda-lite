/**
 * RegistryPanel.jsx — Model Registry: versiona y promueve modelos a producción.
 *
 * Cierra el ciclo MLOps de un producto de inferencia: registras una versión de
 * modelo (con su score de evaluación), la promueves staging → production, y la
 * app sirve exactamente la versión en producción (con el toggle activado).
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import InfoButton from './InfoButton.jsx'
import { t } from '../stores/i18n.js'
import {
  serveProduction, setServeProduction,
} from '../stores/settings.js'

const STAGE_COLOR = {
  production: 'var(--green)',
  staging:    'var(--blue)',
  archived:   'var(--text-3)',
  none:       'var(--text-3)',
}

export default function RegistryPanel() {
  const [versions, setVersions] = createSignal([])
  const [models, setModels]     = createSignal([])
  const [form, setForm]         = createSignal({ model: '', notes: '' })
  const [adding, setAdding]     = createSignal(false)
  const [busy, setBusy]         = createSignal(false)

  async function load() {
    try {
      const r = await axios.get('/api/registry')
      setVersions(r.data.versions || [])
    } catch { /* noop */ }
  }
  async function loadModels() {
    try {
      const r = await axios.get('/api/models/ollama')
      setModels((r.data.models || []).map(m => m.name || m.model || m))
    } catch { /* noop */ }
  }
  onMount(() => { load(); loadModels() })

  async function register() {
    const f = form()
    if (!f.model.trim()) return
    setBusy(true)
    try {
      await axios.post('/api/registry', { model: f.model.trim(), notes: f.notes })
      setForm({ model: '', notes: '' })
      setAdding(false)
      await load()
    } finally { setBusy(false) }
  }

  async function promote(id, stage) {
    setBusy(true)
    try { await axios.post(`/api/registry/${encodeURIComponent(id)}/promote`, { stage }); await load() }
    finally { setBusy(false) }
  }
  async function remove(id) {
    setBusy(true)
    try { await axios.delete(`/api/registry/${encodeURIComponent(id)}`); await load() }
    finally { setBusy(false) }
  }

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <div style="font-size:22px;font-weight:700">{t('reg.title')}</div>
        <InfoButton title={t('reg.title')} intro={t('info.reg.intro')} tip={t('info.reg.tip')} items={[
          { h: t('info.reg.1h'), d: t('info.reg.1d') },
          { h: t('info.reg.2h'), d: t('info.reg.2d') },
          { h: t('info.reg.3h'), d: t('info.reg.3d') },
          { h: t('info.reg.4h'), d: t('info.reg.4d') },
        ]} />
      </div>
      <p style="font-size:13px;color:var(--text-2);margin:0 0 18px;line-height:1.5">{t('reg.subtitle')}</p>

      {/* Toggle: servir el modelo de producción */}
      <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:18px">
        <div>
          <div style="font-size:13px;font-weight:600;color:var(--text-1)">{t('reg.serve_prod')}</div>
          <div style="font-size:12px;color:var(--text-3);margin-top:2px">{t('reg.serve_prod_desc')}</div>
        </div>
        <button onClick={() => setServeProduction(!serveProduction())}
          style={`position:relative;width:44px;height:25px;border-radius:13px;border:none;cursor:pointer;flex-shrink:0;transition:background .2s;background:${serveProduction() ? 'var(--green)' : 'var(--surface-2,rgba(150,150,158,0.3))'}`}>
          <span style={`position:absolute;top:2px;left:${serveProduction() ? '21px' : '2px'};width:21px;height:21px;border-radius:50%;background:#fff;transition:left .2s`} />
        </button>
      </div>

      {/* Registrar nueva versión */}
      <Show when={adding()} fallback={
        <button class="btn btn-primary" style="margin-bottom:18px" onClick={() => setAdding(true)}>+ {t('reg.register')}</button>
      }>
        <div class="card" style="margin-bottom:18px">
          <div style="font-size:14px;font-weight:700;margin-bottom:12px">{t('reg.register')}</div>
          <select value={form().model} onChange={e => setForm({ ...form(), model: e.target.value })}
            style="width:100%;padding:9px;border-radius:9px;background:var(--inset-surface);border:1px solid var(--glass-border);color:var(--text-1);margin-bottom:8px;font-size:13px">
            <option value="">{t('reg.pick_model')}</option>
            <For each={models()}>{m => <option value={m} selected={form().model === m}>{m}</option>}</For>
          </select>
          <input value={form().notes} onInput={e => setForm({ ...form(), notes: e.target.value })}
            placeholder={t('reg.notes_ph')}
            style="width:100%;padding:9px;border-radius:9px;background:var(--inset-surface);border:1px solid var(--glass-border);color:var(--text-1);margin-bottom:12px;font-size:13px" />
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" disabled={busy() || !form().model} onClick={register}>{t('reg.save')}</button>
            <button class="btn" onClick={() => { setAdding(false); setForm({ model: '', notes: '' }) }}>{t('common.cancel')}</button>
          </div>
        </div>
      </Show>

      {/* Lista de versiones */}
      <Show when={versions().length > 0} fallback={<div style="color:var(--text-3);font-size:13px;text-align:center;padding:32px">{t('reg.empty')}</div>}>
        <div style="display:flex;flex-direction:column;gap:12px">
          <For each={versions()}>
            {(v) => (
              <div class="card">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:9px;min-width:0">
                    <span style="font-family:var(--mono);font-size:14px;color:var(--text-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{v.model}</span>
                    <span style="font-size:11px;color:var(--text-3)">{v.version}</span>
                  </div>
                  <span style={`font-size:10px;font-weight:700;padding:2px 9px;border-radius:10px;text-transform:uppercase;letter-spacing:0.03em;color:${STAGE_COLOR[v.stage]};background:color-mix(in srgb, ${STAGE_COLOR[v.stage]} 14%, transparent)`}>{t('reg.stage_' + v.stage)}</span>
                </div>
                <div style="display:flex;align-items:center;gap:12px;font-size:12px;color:var(--text-3);margin-bottom:10px">
                  <Show when={v.eval_score != null}><span>★ {t('reg.score')}: <b style="color:var(--text-2)">{v.eval_score}/5</b></span></Show>
                  <Show when={v.notes}><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{v.notes}</span></Show>
                </div>
                <div style="display:flex;gap:7px;flex-wrap:wrap">
                  <Show when={v.stage !== 'production'}>
                    <button class="btn" style="font-size:12px;padding:5px 11px" disabled={busy()} onClick={() => promote(v.id, 'production')}>{t('reg.to_prod')}</button>
                  </Show>
                  <Show when={v.stage !== 'staging'}>
                    <button class="btn" style="font-size:12px;padding:5px 11px" disabled={busy()} onClick={() => promote(v.id, 'staging')}>{t('reg.to_staging')}</button>
                  </Show>
                  <Show when={v.stage !== 'archived'}>
                    <button class="btn" style="font-size:12px;padding:5px 11px" disabled={busy()} onClick={() => promote(v.id, 'archived')}>{t('reg.to_archived')}</button>
                  </Show>
                  <button class="btn" style="font-size:12px;padding:5px 11px;color:var(--red)" disabled={busy()} onClick={() => remove(v.id)}>{t('common.delete')}</button>
                </div>
              </div>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}
