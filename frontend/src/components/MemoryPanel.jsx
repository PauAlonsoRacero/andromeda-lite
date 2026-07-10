/**
 * MemoryPanel.jsx — Memoria estilo Claude: UN solo bloque de texto cohesivo
 * con lo que Andromeda sabe del usuario (nombre, idioma, stack, preferencias),
 * no una lista de declaraciones sueltas.
 *
 * - Se genera sola al chatear (si el toggle "Generar memoria" está activo).
 * - Los hechos del mismo tipo se REEMPLAZAN (catalán sustituye a alemán).
 * - El usuario puede editar el bloque entero a mano; su texto manda.
 */
import { createSignal, onMount, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import InfoButton from './InfoButton.jsx'

export default function MemoryPanel() {
  const [profile, setProfile] = createSignal(null)   // {text, facts, manual, updated_at, is_empty}
  const [loading, setLoading] = createSignal(true)
  const [editing, setEditing] = createSignal(false)
  const [draft, setDraft]     = createSignal('')
  const [saving, setSaving]   = createSignal(false)
  const [toast, setToast]     = createSignal(null)

  function flash(type, text) {
    setToast({ type, text }); setTimeout(() => setToast(null), 3000)
  }

  onMount(load)
  async function load() {
    setLoading(true)
    try {
      const r = await axios.get('/api/memory/profile')
      setProfile(r.data)
    } catch { setProfile({ text: '', is_empty: true }) }
    setLoading(false)
  }

  function startEdit() {
    setDraft(profile()?.text || '')
    setEditing(true)
  }

  async function save() {
    setSaving(true)
    try {
      const r = await axios.put('/api/memory/profile', { text: draft() })
      setProfile(r.data)
      setEditing(false)
      flash('ok', t('mem.saved'))
    } catch {
      flash('err', t('mem.save_err'))
    }
    setSaving(false)
  }

  async function clearAll() {
    if (!confirm(t('mem.clear_confirm'))) return
    try {
      await axios.delete('/api/memory/profile')
      await load()
      flash('ok', t('mem.cleared'))
    } catch { flash('err', t('mem.save_err')) }
  }

  const updatedLabel = () => {
    const u = profile()?.updated_at
    if (!u) return ''
    try { return new Date(u).toLocaleString() } catch { return '' }
  }

  return (
    <div class="panel-page" style="max-width:760px">
      <div class="panel-page-header">
        <div>
          <div style="display:flex;align-items:center;gap:9px"><div class="panel-page-title">{t('mem.title')}</div><InfoButton title={t('mem.title')} intro={t('info.mem.intro')} tip={t('info.mem.tip')} items={[
            { h: t('info.mem.1h'), d: t('info.mem.1d') },
            { h: t('info.mem.2h'), d: t('info.mem.2d') },
            { h: t('info.mem.3h'), d: t('info.mem.3d') },
            { h: t('info.mem.4h'), d: t('info.mem.4d') },
          ]} /></div>
          <div class="panel-page-sub">{t('mem.subtitle')}</div>
        </div>
        <button class="btn btn-ghost" onClick={load} title={t('mem.refresh')}>↺</button>
      </div>

      <Show when={!loading()} fallback={
        <div class="card" style="text-align:center;padding:40px"><div class="spin" style="width:20px;height:20px;margin:0 auto" /></div>
      }>
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:14px;font-weight:700;color:var(--text-1)">{t('mem.block_title')}</div>
            <Show when={!editing()}>
              <button class="btn btn-ghost btn-sm" onClick={startEdit}>{t('mem.edit')}</button>
            </Show>
          </div>

          {/* Modo lectura: bloque de texto cohesivo (estilo Claude) */}
          <Show when={!editing()}>
            <Show when={!profile()?.is_empty} fallback={
              <div style="padding:24px 4px;color:var(--text-3);font-size:13px;line-height:1.6">
                {t('mem.empty_block')}
              </div>
            }>
              <div style="font-size:14px;line-height:1.7;color:var(--text-1);white-space:pre-wrap">
                {profile()?.text}
              </div>
              <Show when={updatedLabel()}>
                <div style="margin-top:14px;font-size:11px;color:var(--text-3)">
                  {t('mem.updated')} · {updatedLabel()}
                </div>
              </Show>
            </Show>
          </Show>

          {/* Modo edición: textarea con todo el bloque */}
          <Show when={editing()}>
            <textarea
              class="g-input"
              value={draft()}
              onInput={e => setDraft(e.target.value)}
              placeholder={t('mem.edit_ph')}
              rows={8}
              style="width:100%;resize:vertical;font-size:14px;line-height:1.7"
            />
            <div style="display:flex;gap:8px;margin-top:12px">
              <button class="btn btn-primary" onClick={save} disabled={saving()}>
                {saving() ? '…' : t('mem.save')}
              </button>
              <button class="btn btn-ghost" onClick={() => setEditing(false)} disabled={saving()}>
                {t('mem.cancel')}
              </button>
            </div>
          </Show>

          <Show when={toast()}>
            <div style={`margin-top:12px;font-size:12px;padding:8px 12px;border-radius:var(--r-sm);${toast().type === 'ok' ? 'background:rgba(52,211,153,.12);color:var(--green)' : 'background:rgba(248,113,113,.12);color:var(--red)'}`}>
              {toast().text}
            </div>
          </Show>
        </div>

        {/* Acciones de gestión */}
        <Show when={!profile()?.is_empty && !editing()}>
          <div style="display:flex;justify-content:flex-end;margin-top:12px">
            <button class="btn btn-danger btn-sm" onClick={clearAll}>{t('mem.clear')}</button>
          </div>
        </Show>
      </Show>
    </div>
  )
}
