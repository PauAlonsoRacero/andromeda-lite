/**
 * SkillsPanel — Skills disponibles.
 *
 * Las skills son paquetes de instrucciones que Andromeda activa por su cuenta
 * cuando el prompt encaja con su descripción. Este panel las lista, permite ver
 * qué contienen y probar qué activaría una frase concreta.
 */
import { createSignal, createResource, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import { errorMessage } from '../services/errors.js'
import { notifyChange } from '../stores/events.js'

export default function SkillsPanel() {
  const [skills, { refetch }] = createResource(async () =>
    (await axios.get('/api/skills')).data.skills || [])
  const [open, setOpen] = createSignal(null)
  const [detail, setDetail] = createSignal(null)
  const [probe, setProbe] = createSignal('')
  const [probeHit, setProbeHit] = createSignal(null)
  const [creating, setCreating] = createSignal(false)
  const [form, setForm] = createSignal({ name: '', description: '', triggers: '', body: '' })
  const [err, setErr] = createSignal('')

  async function saveSkill() {
    const f = form()
    if (!f.name.trim() || !f.description.trim()) {
      setErr(t('skills.need_fields')); return
    }
    try {
      await axios.post('/api/skills/user', { id: f.name, ...f })
      setCreating(false); setErr('')
      setForm({ name: '', description: '', triggers: '', body: '' })
      refetch(); notifyChange('skills')
    } catch (e) { setErr(errorMessage(e) || 'Error') }
  }
  async function removeSkill(id, ev) {
    ev.stopPropagation()
    await axios.delete(`/api/skills/user/${encodeURIComponent(id)}`)
    refetch()
  }

  async function toggle(id) {
    if (open() === id) { setOpen(null); return }
    setOpen(id)
    setDetail((await axios.get(`/api/skills/${id}`)).data)
  }
  async function testProbe() {
    if (!probe().trim()) return
    const r = await axios.get('/api/skills/match', { params: { q: probe() } })
    setProbeHit(r.data.matched || [])
  }

  return (
    <div class="card" style="padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <h3 style="margin:0;font-size:var(--fs-base)">⚡ {t('skills.title')}</h3>
        <div style="display:flex;gap:6px">
          <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:3px 10px"
                  onClick={() => setCreating(!creating())}>
            {creating() ? t('chat.close') : '+ ' + t('skills.create')}
          </button>
          <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:3px 10px"
                  onClick={async () => { await axios.post('/api/skills/reload'); refetch() }}>
            {t('skills.reload')}
          </button>
        </div>
      </div>
      <p style="font-size:var(--fs-sm);color:var(--text-3);margin:0 0 12px">{t('skills.desc')}</p>

      <Show when={creating()}>
        <div style="background:var(--bg-2);border-radius:14px;padding:12px;margin-bottom:10px;display:flex;flex-direction:column;gap:8px">
          <input aria-label={t('skills.f_name')} placeholder={t('skills.f_name')} value={form().name}
                 onInput={e => setForm({ ...form(), name: e.target.value })}
                 style="background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1)" />
          <input aria-label={t('skills.f_desc')} placeholder={t('skills.f_desc')} value={form().description}
                 onInput={e => setForm({ ...form(), description: e.target.value })}
                 style="background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1)" />
          <input aria-label={t('skills.f_triggers')} placeholder={t('skills.f_triggers')} value={form().triggers}
                 onInput={e => setForm({ ...form(), triggers: e.target.value })}
                 style="background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1)" />
          <textarea placeholder={t('skills.f_body')} rows={4} value={form().body}
                    onInput={e => setForm({ ...form(), body: e.target.value })}
                    style="background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1);resize:vertical;font-family:var(--font)" />
          <Show when={err()}><div style="font-size:var(--fs-xs);color:#f87171">{err()}</div></Show>
          <button class="btn btn-glass" style="font-size:var(--fs-sm);align-self:flex-start" onClick={saveSkill}>
            {t('skills.save')}
          </button>
        </div>
      </Show>

      <div style="display:flex;flex-direction:column;gap:6px">
        <For each={skills()}>{s => (
          <div style="background:var(--bg-2);border-radius:10px;overflow:hidden">
            <div onClick={() => toggle(s.id)}
                 style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 12px;cursor:pointer">
              <div style="min-width:0">
                <div style="font-size:var(--fs-base);font-weight:600;color:var(--text-1);display:flex;align-items:center;gap:6px">
                  {s.name}
                  <Show when={s.user_created}>
                    <span style="font-size:var(--fs-micro);color:var(--purple, #a78bfa);border:1px solid currentColor;border-radius:6px;padding:0 4px">{t('skills.mine')}</span>
                  </Show>
                </div>
                <div style="font-size:var(--fs-xs);color:var(--text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  {s.description}
                </div>
              </div>
              <span style="display:flex;align-items:center;gap:6px;flex-shrink:0">
                <Show when={s.user_created}>
                  <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:2px 7px"
                          title={t('skills.delete')} onClick={e => removeSkill(s.id, e)}>✕</button>
                </Show>
                <span style="color:var(--text-3);font-size:var(--fs-sm)">{open() === s.id ? '▾' : '▸'}</span>
              </span>
            </div>
            <Show when={open() === s.id && detail()}>
              <pre style="margin:0;padding:12px;background:var(--inset-surface);font-size:var(--fs-xs);
                          color:var(--text-2);white-space:pre-wrap;max-height:220px;overflow-y:auto;
                          font-family:var(--font);border-top:1px solid var(--glass-border)">{detail().body}</pre>
            </Show>
          </div>
        )}</For>
      </div>

      <div style="display:flex;gap:6px;margin-top:12px">
        <input value={probe()} onInput={e => setProbe(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && testProbe()}
               placeholder={t('skills.probe_ph')}
               style="flex:1;background:var(--bg-2);border:1px solid var(--glass-border);
                      border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1)" />
        <button class="btn btn-glass" style="font-size:var(--fs-sm)" onClick={testProbe}>{t('skills.probe_btn')}</button>
      </div>
      <Show when={probeHit() !== null}>
        <div style="font-size:var(--fs-xs);color:var(--text-3);margin-top:6px">
          {probeHit().length
            ? `${t('skills.would_activate')}: ${probeHit().map(m => m.name).join(', ')}`
            : t('skills.no_activation')}
        </div>
      </Show>
    </div>
  )
}
