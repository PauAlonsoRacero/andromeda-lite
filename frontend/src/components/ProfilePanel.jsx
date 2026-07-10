/**
 * ProfilePanel.jsx — Perfil de la cuenta. Permite completar/editar datos
 * (nombre visible, email, ubicación, organización) y cambiar la contraseña.
 * Los datos se guardan en el backend vía /api/auth/profile.
 */
import { createSignal, onMount, Show } from 'solid-js'
import axios from 'axios'
import { session, setSession, logout } from '../stores/auth'
import { editionLabel, isPro } from '../stores/edition'
import { t } from '../stores/i18n.js'

export default function ProfilePanel(props) {
  const [name, setName]       = createSignal('')
  const [email, setEmail]     = createSignal('')
  const [location, setLocation] = createSignal('')
  const [org, setOrg]         = createSignal('')
  const [loading, setLoading] = createSignal(true)
  const [saving, setSaving]   = createSignal(false)
  const [msg, setMsg]         = createSignal(null)

  // Cambio de contraseña
  const [curPw, setCurPw]     = createSignal('')
  const [newPw, setNewPw]     = createSignal('')
  const [pwMsg, setPwMsg]     = createSignal(null)
  const [pwBusy, setPwBusy]   = createSignal(false)

  // RGPD
  const [gdprBusy, setGdprBusy] = createSignal(false)
  const [gdprMsg, setGdprMsg]   = createSignal(null)

  async function exportData() {
    setGdprBusy(true); setGdprMsg(null)
    try {
      const r = await axios.get('/api/cloud/export')
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'andromeda-mis-datos.json'; a.click()
      URL.revokeObjectURL(url)
      setGdprMsg('✓ Datos descargados')
    } catch (e) {
      setGdprMsg('No se pudieron descargar los datos')
    }
    setGdprBusy(false)
  }

  async function deleteAccount() {
    if (!confirm('¿Eliminar tu cuenta y todos tus datos? Esta acción es permanente y no se puede deshacer.')) return
    if (!confirm('Confirmación final: tu cuenta, suscripción y licencias se eliminarán para siempre. ¿Continuar?')) return
    setGdprBusy(true); setGdprMsg(null)
    try {
      await axios.delete('/api/cloud/account')
      logout()
    } catch (e) {
      setGdprMsg('No se pudo eliminar la cuenta')
      setGdprBusy(false)
    }
  }

  onMount(async () => {
    try {
      const r = await axios.get('/api/auth/profile')
      const p = r.data.profile || {}
      setName(p.display_name || session()?.username || '')
      setEmail(p.email || '')
      setLocation(p.location || '')
      setOrg(p.organization || '')
    } catch {
      setName(session()?.username || '')
    }
    setLoading(false)
  })

  async function save() {
    setSaving(true); setMsg(null)
    try {
      await axios.put('/api/auth/profile', {
        display_name: name(), email: email(), location: location(), organization: org(),
      })
      setMsg('✓ Datos guardados')
      setTimeout(() => setMsg(null), 3000)
    } catch (e) {
      setMsg('Error: ' + (e.response?.data?.error || e.message))
    }
    setSaving(false)
  }

  async function changePassword() {
    if (newPw().length < 8) { setPwMsg('La nueva contraseña debe tener al menos 8 caracteres'); return }
    setPwBusy(true); setPwMsg(null)
    try {
      await axios.post('/api/auth/change-password', { current_password: curPw(), new_password: newPw() })
      setPwMsg('✓ Contraseña actualizada')
      setCurPw(''); setNewPw('')
      setTimeout(() => setPwMsg(null), 3000)
    } catch (e) {
      setPwMsg('Error: ' + (e.response?.data?.error || 'No se pudo cambiar'))
    }
    setPwBusy(false)
  }

  const plan = () => (session()?.plan || 'free').toUpperCase()

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px">
        <div style="width:56px;height:56px;border-radius:50%;background:var(--grad-primary);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:22px;color:#fff;flex-shrink:0">
          {(name() || session()?.username || '?')[0].toUpperCase()}
        </div>
        <div>
          <div style="font-size:22px;font-weight:700">{name() || session()?.username}</div>
          <div style="font-size:12px;color:var(--text-3)">
            Plan <span style={`font-weight:700;${plan()==='PRO'?'color:var(--purple)':'color:var(--text-2)'}`}>{plan()}</span> · {editionLabel()}
          </div>
        </div>
      </div>

      <Show when={!loading()}>
        {/* Datos de la cuenta */}
        <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 12px">{t('ui2.account_data')}</div>
        <div style="display:flex;flex-direction:column;gap:14px">
          <Field label={t('prof.display_name')} value={name()} onInput={setName} placeholder={t('prof.ph_yourname')} />
          <Field label="Email" value={email()} onInput={setEmail} placeholder={t('prof.ph_email')} type="email" />
          <Field label={t('prof.location')} value={location()} onInput={setLocation} placeholder={t('prof.ph_city')} />
          <Field label={t('prof.organization')} value={org()} onInput={setOrg} placeholder={t('prof.ph_company')} />
        </div>
        <div style="display:flex;align-items:center;gap:14px;margin-top:16px">
          <button class="btn btn-primary" onClick={save} disabled={saving()}>
            {saving() ? '…' : 'Guardar cambios'}
          </button>
          <Show when={msg()}><span style="font-size:13px;color:var(--text-2)">{msg()}</span></Show>
        </div>

        {/* Cambiar contraseña */}
        <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:32px 0 12px">{t('prof.security')}</div>
        <div style="display:flex;flex-direction:column;gap:14px;max-width:420px">
          <Field label={t('prof.cur_pw')} value={curPw()} onInput={setCurPw} type="password" placeholder="••••••••" />
          <Field label={t('prof.new_pw')} value={newPw()} onInput={setNewPw} type="password" placeholder={t('prof.ph_min8')} />
        </div>
        <div style="display:flex;align-items:center;gap:14px;margin-top:16px">
          <button class="btn btn-glass" onClick={changePassword} disabled={pwBusy()}>
            {pwBusy() ? '…' : 'Cambiar contraseña'}
          </button>
          <Show when={pwMsg()}><span style="font-size:13px;color:var(--text-2)">{pwMsg()}</span></Show>
        </div>

        {/* Plan */}
        <Show when={plan() !== 'PRO'}>
          <div style="margin-top:32px;padding:16px;border-radius:14px;background:var(--inset-surface);border:1px solid var(--glass-border)">
            <div style="font-size:14px;font-weight:700;margin-bottom:4px">{t('prof.want_more')}</div>
            <div style="font-size:12.5px;color:var(--text-3);line-height:1.6">
              Andromeda Pro añade orquestación multi-IA, MLOps, fine-tuning y multiusuario. La suscripción estará disponible próximamente.
            </div>
          </div>
        </Show>

        <div style="margin-top:28px">
          <button class="btn btn-ghost" style="font-size:13px;color:var(--red)" onClick={logout}>{t('prof.logout')}</button>
        </div>

        {/* Privacidad / RGPD */}
        <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:32px 0 12px">{t('ui2.privacy_data')}</div>
        <div style="font-size:12.5px;color:var(--text-3);line-height:1.6;margin-bottom:14px">
          Puedes descargar todos tus datos o eliminar tu cuenta en cualquier momento. Tus conversaciones y modelos nunca salen de tu equipo; solo tu cuenta se guarda en la nube.
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          <button class="btn btn-glass" onClick={exportData} disabled={gdprBusy()}>{t('ui2.download_data')}</button>
          <button class="btn btn-ghost" style="color:var(--red)" onClick={deleteAccount} disabled={gdprBusy()}>{t('ui2.delete_account')}</button>
        </div>
        <Show when={gdprMsg()}><div style="font-size:13px;color:var(--text-2);margin-top:10px">{gdprMsg()}</div></Show>
      </Show>
    </div>
  )
}

function Field(props) {
  return (
    <label style="display:flex;flex-direction:column;gap:6px">
      <span style="font-size:12.5px;color:var(--text-2);font-weight:600">{props.label}</span>
      <input
        class="g-input"
        type={props.type || 'text'}
        value={props.value}
        placeholder={props.placeholder}
        onInput={e => props.onInput(e.target.value)}
        style="padding:10px 12px;border-radius:10px;background:var(--field-bg);border:1px solid var(--glass-border);color:var(--text-1);font-family:var(--font);font-size:14px"
      />
    </label>
  )
}
