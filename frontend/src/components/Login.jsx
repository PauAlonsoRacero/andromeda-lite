/**
 * Login.jsx — Puerta de entrada. Registro e inicio de sesión contra Andromeda
 * Cloud (cualquiera que se registre queda en el servicio). La sesión persiste
 * en local y el plan (Lite/Pro) se deriva de la licencia firmada.
 */
import { createSignal, Show } from 'solid-js'
import axios from 'axios'
import { setSession } from '../stores/auth'
import { t } from '../stores/i18n.js'

export default function Login(props) {
  const [mode, setMode] = createSignal('login')     // login | register
  const [email, setEmail] = createSignal('')
  const [password, setPassword] = createSignal('')
  const [name, setName] = createSignal('')
  const [accept, setAccept] = createSignal(false)
  const [error, setError] = createSignal('')
  const [busy, setBusy] = createSignal(false)
  const [remember, setRemember] = createSignal(true)

  function validEmail(s) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s) }

  async function submit(e) {
    e?.preventDefault?.()
    if (busy()) return
    setError('')
    if (!validEmail(email())) { setError(t('js.email_invalid')); return }
    if (password().length < 8) { setError(t('js.pass_min8')); return }
    if (mode() === 'register' && !accept()) { setError(t('js.accept_terms')); return }

    setBusy(true)
    try {
      const payload = mode() === 'register'
        ? { email: email(), password: password(), display_name: name() }
        : { email: email(), password: password() }
      const r = await axios.post(`/api/cloud/${mode()}`, payload)
      const u = r.data.user
      setSession({ token: 'cloud', username: u.display_name || u.email, email: u.email, plan: r.data.plan }, remember())
      props.onClose?.()   // cerrar el login si se abrió manualmente desde Configuración
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo conectar con el servicio. ¿Tienes conexión?')
    }
    setBusy(false)
  }

  return (
    <div class="login-page">
      <div class="login-card anim-slide" style="position:relative">
        <Show when={props.canClose}>
          <button onClick={() => props.onClose?.()} title={t('login.close')}
            style="position:absolute;top:14px;right:14px;width:32px;height:32px;border-radius:50%;border:none;background:var(--hover-surface);color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;font-family:var(--font)">×</button>
        </Show>
        <img src="/andromeda-logo.png" alt="" style="width:54px;height:54px;object-fit:contain;margin:0 auto 14px;display:block" />
        <h1 class="login-title">Andromeda</h1>
        <div class="login-sub">
          {mode() === 'login' ? t('login.signin') : 'Crea tu cuenta'}
        </div>

        <Show when={mode() === 'register'}>
          <input class="g-input login-input" placeholder={t('login.ph_name')} value={name()}
            onInput={e => setName(e.target.value)} autocomplete="name"
            onKeyDown={e => e.key === 'Enter' && submit()} />
        </Show>

        <input class="g-input login-input" type="email" placeholder={t('login.ph_email')} value={email()}
          onInput={e => setEmail(e.target.value)} autocomplete="email"
          onKeyDown={e => e.key === 'Enter' && submit()} />
        <input class="g-input login-input" type="password" placeholder={t('login.ph_pass')} value={password()}
          onInput={e => setPassword(e.target.value)}
          autocomplete={mode() === 'login' ? 'current-password' : 'new-password'}
          onKeyDown={e => e.key === 'Enter' && submit()} />

        <Show when={mode() === 'login'}>
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-2);cursor:pointer;margin:2px 2px 4px">
            <input type="checkbox" checked={remember()} onChange={e => setRemember(e.target.checked)}
              style="width:16px;height:16px;accent-color:var(--blue);cursor:pointer" />
            Recordarme en este dispositivo (30 días)
          </label>
        </Show>

        <Show when={mode() === 'register'}>
          <label style="display:flex;align-items:flex-start;gap:8px;font-size:12px;color:var(--text-2);cursor:pointer;margin:2px 2px 4px;line-height:1.5">
            <input type="checkbox" checked={accept()} onChange={e => setAccept(e.target.checked)}
              style="width:16px;height:16px;accent-color:var(--blue);cursor:pointer;margin-top:1px;flex-shrink:0" />
            <span>Acepto los <a href="https://andromeda.app/terms" target="_blank" style="color:var(--blue)">{t('login.terms')}</a> y la <a href="https://andromeda.app/privacy" target="_blank" style="color:var(--blue)">{t('login.privacy_policy')}</a>.</span>
          </label>
        </Show>

        <Show when={error()}>
          <div class="login-error">{error()}</div>
        </Show>

        <button class="btn btn-primary login-btn" disabled={busy()} onClick={submit}>
          {busy() ? '…' : mode() === 'login' ? 'Entrar' : 'Crear cuenta'}
        </button>

        <div class="login-switch">
          {mode() === 'login'
            ? <>{t('login.no_account')}<a onClick={() => { setMode('register'); setError('') }}>{t('login.signup')}</a></>
            : <>{t('login.have_account')}<a onClick={() => { setMode('login'); setError('') }}>{t('login.signin')}</a></>}
        </div>
        <div class="login-note">{t('login.privacy_note')}</div>
      </div>
    </div>
  )
}
