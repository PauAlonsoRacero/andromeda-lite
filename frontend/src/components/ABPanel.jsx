/**
 * ABPanel.jsx — Gestión de experimentos A/B de modelos.
 * Crea experimentos (modelo A vs B con pesos), los activa, y muestra resultados
 * con veredicto estadístico (no "a ojo": test z + muestra mínima).
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import InfoButton from './InfoButton.jsx'
import { t } from '../stores/i18n.js'

export default function ABPanel() {
  const [experiments, setExperiments] = createSignal([])
  const [models, setModels] = createSignal([])
  const [results, setResults] = createSignal({})   // {exp_id: result}
  const [creating, setCreating] = createSignal(false)
  const [form, setForm] = createSignal({ id: '', a: '', b: '', weight: 50 })

  onMount(() => { load(); loadModels() })

  async function load() {
    try {
      const r = await axios.get('/api/ab')
      setExperiments(r.data.experiments || [])
      for (const e of r.data.experiments || []) loadResults(e.id)
    } catch {}
  }
  async function loadModels() {
    try {
      const r = await axios.get('/api/models/ollama')
      setModels(r.data.models || [])
    } catch {}
  }
  async function loadResults(id) {
    try {
      const r = await axios.get(`/api/ab/${encodeURIComponent(id)}/results`)
      setResults(prev => ({ ...prev, [id]: r.data }))
    } catch {}
  }

  async function create() {
    const f = form()
    if (!f.id.trim() || !f.a || !f.b) return
    await axios.post('/api/ab', {
      id: f.id.trim(),
      variants: [
        { name: 'A', model: f.a, weight: Number(f.weight) },
        { name: 'B', model: f.b, weight: 100 - Number(f.weight) },
      ],
    })
    setForm({ id: '', a: '', b: '', weight: 50 })
    setCreating(false)
    load()
  }
  async function toggleActive(e) {
    await axios.post(`/api/ab/${encodeURIComponent(e.id)}/active`, { active: !e.active })
    load()
  }
  async function remove(id) {
    if (!confirm(t('ab.delete_confirm'))) return
    await axios.delete(`/api/ab/${encodeURIComponent(id)}`)
    load()
  }

  const Bar = (props) => (
    <div style="height:8px;border-radius:4px;background:var(--surface-2);overflow:hidden;margin-top:4px">
      <div style={`height:100%;width:${props.pct}%;background:${props.color}`} />
    </div>
  )

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <div style="font-size:22px;font-weight:700">{t('ab.title')}</div>
        <InfoButton title={t('ab.title')} intro={t('info.ab.intro')} tip={t('info.ab.tip')} items={[
          { h: t('info.ab.1h'), d: t('info.ab.1d') },
          { h: t('info.ab.2h'), d: t('info.ab.2d') },
          { h: t('info.ab.3h'), d: t('info.ab.3d') },
          { h: t('info.ab.4h'), d: t('info.ab.4d') },
        ]} />
      </div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:18px">{t('ab.sub')}</div>

      <Show when={!creating()}>
        <button class="btn btn-primary" onClick={() => setCreating(true)}>{t('ab.new')}</button>
      </Show>

      {/* Formulario de creación */}
      <Show when={creating()}>
        <div class="card">
          <div class="card-title">{t('ab.new')}</div>
          <input class="g-input" placeholder={t('ab.name_ph')} value={form().id}
            onInput={e => setForm({ ...form(), id: e.target.value })} style="width:100%;margin-bottom:10px" />
          <div style="display:flex;gap:10px;margin-bottom:10px">
            <select class="g-input" style="flex:1" onChange={e => setForm({ ...form(), a: e.target.value })}>
              <option value="">{t('ab.model_a')}</option>
              <For each={models()}>{m => <option value={m} selected={form().a === m}>{m}</option>}</For>
            </select>
            <select class="g-input" style="flex:1" onChange={e => setForm({ ...form(), b: e.target.value })}>
              <option value="">{t('ab.model_b')}</option>
              <For each={models()}>{m => <option value={m} selected={form().b === m}>{m}</option>}</For>
            </select>
          </div>
          <div style="font-size:12px;color:var(--text-3);margin-bottom:6px">{t('ab.split')}: A {form().weight}% · B {100 - form().weight}%</div>
          <input type="range" min="10" max="90" step="10" value={form().weight}
            onInput={e => setForm({ ...form(), weight: e.target.value })} style="width:100%;margin-bottom:12px" />
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" onClick={create} disabled={!form().id.trim() || !form().a || !form().b}>{t('ab.create')}</button>
            <button class="btn btn-ghost" onClick={() => setCreating(false)}>{t('mem.cancel')}</button>
          </div>
        </div>
      </Show>

      {/* Lista de experimentos */}
      <div class="stagger" style="display:flex;flex-direction:column;gap:14px;margin-top:14px">
        <For each={experiments()}>
          {(e) => {
            const res = () => results()[e.id]
            return (
              <div class="card">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
                  <div style="display:flex;align-items:center;gap:10px">
                    <span style="font-size:15px;font-weight:700">{e.id}</span>
                    <span style={`font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;${e.active ? 'background:rgba(52,211,153,.15);color:var(--green)' : 'background:var(--surface-2);color:var(--text-3)'}`}>
                      {e.active ? t('ab.active') : t('ab.paused')}
                    </span>
                  </div>
                  <div style="display:flex;gap:6px">
                    <button class="btn btn-ghost btn-sm" onClick={() => toggleActive(e)}>{e.active ? t('ab.pause') : t('ab.activate')}</button>
                    <button class="btn btn-ghost btn-sm" style="color:var(--red)" onClick={() => remove(e.id)}>✕</button>
                  </div>
                </div>

                <Show when={res()}>
                  <For each={Object.entries(res().variants)}>
                    {([name, v]) => (
                      <div style="margin-bottom:12px">
                        <div style="display:flex;justify-content:space-between;font-size:13px">
                          <span><b>{name}</b> · <span style="font-family:var(--mono);color:var(--text-2)">{v.model}</span></span>
                          <span style="color:var(--text-3)">{v.requests} req · {v.success_rate}% · {v.avg_latency_ms}ms</span>
                        </div>
                        <Bar pct={v.success_rate} color={res().winner === name ? 'var(--green)' : 'var(--blue)'} />
                        <Show when={v.satisfaction != null}>
                          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-3);margin-top:6px">
                            <span>👍 {t('ab.satisfaction')}</span>
                            <span>{v.satisfaction}% · {v.positive}/{v.ratings}</span>
                          </div>
                          <Bar pct={v.satisfaction} color="var(--purple)" />
                        </Show>
                      </div>
                    )}
                  </For>

                  {/* Veredicto estadístico */}
                  <div style="margin-top:10px;padding:10px 12px;border-radius:8px;background:var(--surface-1);font-size:12px;line-height:1.6">
                    <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-3);margin-bottom:2px">{t('ab.by_success')}</div>
                    <Show when={res().confident} fallback={
                      <span style="color:var(--text-3)">
                        {res().enough_sample
                          ? t('ab.not_significant')
                          : t('ab.need_more').replace('{n}', res().min_sample)}
                        <Show when={res().leader}> · {t('ab.leading')}: <b>{res().leader}</b></Show>
                      </span>
                    }>
                      <span style="color:var(--green);font-weight:600">
                        ✓ {t('ab.winner')}: <b>{res().winner}</b>
                        <Show when={res().test}> · p = {res().test.p_value}</Show>
                      </span>
                    </Show>
                    {/* Veredicto por CALIDAD (satisfacción 👍/👎) */}
                    <Show when={res().quality_test || res().quality_leader}>
                      <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.04em;color:var(--text-3);margin:8px 0 2px">{t('ab.by_quality')}</div>
                      <Show when={res().quality_confident} fallback={
                        <span style="color:var(--text-3)">
                          {res().quality_enough_sample
                            ? t('ab.not_significant')
                            : t('ab.need_more').replace('{n}', res().quality_min_sample)}
                          <Show when={res().quality_leader}> · {t('ab.leading')}: <b>{res().quality_leader}</b></Show>
                        </span>
                      }>
                        <span style="color:var(--purple);font-weight:600">
                          ★ {t('ab.winner')}: <b>{res().quality_winner}</b>
                          <Show when={res().quality_test}> · p = {res().quality_test.p_value}</Show>
                        </span>
                      </Show>
                    </Show>
                  </div>
                </Show>
              </div>
            )
          }}
        </For>
      </div>

      <Show when={experiments().length === 0 && !creating()}>
        <div style="text-align:center;padding:40px;color:var(--text-3);font-size:13px">{t('ab.empty')}</div>
      </Show>
    </div>
  )
}
