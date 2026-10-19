/**
 * MCPPanel.jsx — Gestión de servidores MCP iOS 26.
 * Activar/desactivar servidores, ver herramientas, reconectar.
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import { errorMessage } from '../services/errors.js'
import { notifyChange } from '../stores/events.js'
import InfoButton from './InfoButton.jsx'

const _ic = (p) => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{p}</svg>
const SERVER_META = {
  filesystem:            { icon: () => _ic(<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>), color: '#fbbf24' },
  fetch:                 { icon: () => _ic(<><circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/></>), color: '#34d399' },
  memory:                { icon: () => _ic(<path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-3 3 3 3 0 0 0 1 5.83V18a3 3 0 0 0 5 2 3 3 0 0 0 5-2v-3.17A3 3 0 0 0 18 9a3 3 0 0 0-3-3 3 3 0 0 0-6 0z"/>), color: '#f87cb8' },
  'sequential-thinking': { icon: () => _ic(<><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.3h6c0-1 .4-1.8 1-2.3A7 7 0 0 0 12 2z"/></>), color: '#a78bfa' },
  git:                   { icon: () => _ic(<><circle cx="12" cy="12" r="3"/><line x1="12" y1="3" x2="12" y2="9"/><line x1="12" y1="15" x2="12" y2="21"/></>), color: '#f0652f' },
  github:                { icon: () => _ic(<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>), color: '#b07cf8' },
  gitlab:                { icon: () => _ic(<path d="m22 13.29-3.33-10a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.11.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18l-2.26 6.67H8.32L6.1 3.26a.42.42 0 0 0-.1-.18.38.38 0 0 0-.26-.08.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18L2 13.29a.74.74 0 0 0 .27.83L12 21l9.69-6.88a.71.71 0 0 0 .31-.83z"/>), color: '#fc6d26' },
  sqlite:                { icon: () => _ic(<><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></>), color: '#0f80cc' },
  postgres:              { icon: () => _ic(<><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></>), color: '#38d6c4' },
  'brave-search':        { icon: () => _ic(<><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></>), color: '#fb542b' },
  puppeteer:             { icon: () => _ic(<><circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/></>), color: '#40b5a4' },
  time:                  { icon: () => _ic(<><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></>), color: '#5b9cf6' },
  everything:            { icon: () => _ic(<><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></>), color: '#9aa0aa' },
  slack:                 { icon: () => _ic(<><rect x="13" y="2" width="3" height="8" rx="1.5"/><rect x="13" y="14" width="3" height="8" rx="1.5"/><rect x="2" y="13" width="8" height="3" rx="1.5"/><rect x="14" y="13" width="8" height="3" rx="1.5"/></>), color: '#e01e5a' },
  'google-drive':        { icon: () => _ic(<><path d="M8 3h8l6 11h-8z"/><path d="m2 14 4-7"/><path d="M8 21h8l3-5H5z"/></>), color: '#1fa463' },
  'google-maps':         { icon: () => _ic(<><path d="M21 10c0 7-9 12-9 12s-9-5-9-12a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></>), color: '#ea4335' },
}

export default function MCPPanel() {
  const [servers, setServers]   = createSignal([])
  const [status, setStatus]     = createSignal(null)
  const [loading, setLoading]   = createSignal(true)
  const [busy, setBusy]         = createSignal(null)
  const [reconnecting, setReconnecting] = createSignal(false)
  const [msg, setMsg]           = createSignal(null)
  const [copied, setCopied]     = createSignal('')
  const [keyDraft, setKeyDraft] = createSignal({})
  const [diag, setDiag]         = createSignal(null)
  const [installing, setInstalling] = createSignal(null)

  /** Instala un runtime que falta (uv se instala solo; Node requiere al usuario). */
  async function installRuntime(rt) {
    setInstalling(rt)
    setMsg(t('mcp.installing').replace('{rt}', rt))
    try {
      const r = await axios.post(`/api/mcp/install-runtime/${rt}`)
      setMsg((r.data.installed ? '✓ ' : '') + r.data.message)
      await loadAll({ silent: true })
      notifyChange('mcp')
    } catch (e) {
      setMsg('Error: ' + (errorMessage(e)))
    } finally {
      setInstalling(null)
    }
  }

  onMount(loadAll)

  /** Guarda una clave de API y reintenta la conexión del servidor que la usa. */
  async function saveKey(keyName) {
    const value = (keyDraft()[keyName] || '').trim()
    if (!value) return
    try {
      await axios.put(`/api/mcp/keys/${encodeURIComponent(keyName)}`, { value })
      setKeyDraft({ ...keyDraft(), [keyName]: '' })
      setMsg(t('mcp.key_saved_msg'))
      await loadAll({ silent: true })
      notifyChange('mcp')
      setTimeout(() => setMsg(null), 4000)
    } catch (e) {
      setMsg('Error: ' + (errorMessage(e)))
    }
  }

  async function removeKey(keyName) {
    try {
      await axios.delete(`/api/mcp/keys/${encodeURIComponent(keyName)}`)
      await loadAll({ silent: true })
      notifyChange('mcp')
    } catch (e) {
      setMsg('Error: ' + (errorMessage(e)))
    }
  }

  async function loadAll(opts = {}) {
    // El spinner solo en la carga inicial. En un refresco tras activar un
    // servidor, sustituir la lista por el spinner colapsa el DOM y el scroll
    // salta al principio, perdiendo al usuario de vista.
    if (!opts.silent) setLoading(true)
    const [srv, st, dg] = await Promise.allSettled([
      axios.get('/api/mcp/servers').then(r => r.data),
      axios.get('/api/mcp/status').then(r => r.data),
      axios.get('/api/mcp/diagnose').then(r => r.data),
    ])
    if (srv.status === 'fulfilled') setServers(srv.value.servers || [])
    if (st.status === 'fulfilled')  setStatus(st.value)
    if (dg.status === 'fulfilled')  setDiag(dg.value)
    if (!opts.silent) setLoading(false)
  }

  async function toggle(id, enabled) {
    setBusy(id)
    setMsg(!enabled ? t('mcp.connecting_first') : null)
    try {
      const r = await axios.put(`/api/mcp/servers/${id}`, { enabled: !enabled })
      // Preferir la clave traducible; el texto del backend es solo respaldo.
      const texto = r.data.message_key
        ? t(r.data.message_key).replace('{count}', r.data.message_args?.count ?? '')
        : (r.data.message || t('mcp.done'))
      setMsg((r.data.connected ? '✓ ' : '') + texto)
      await loadAll({ silent: true })
      notifyChange('mcp')
      setTimeout(() => setMsg(null), 5000)
    } catch (e) {
      setMsg('Error: ' + (errorMessage(e)))
    } finally {
      setBusy(null)
    }
  }

  async function reconnect() {
    setReconnecting(true)
    setMsg(null)
    try {
      await axios.post('/api/mcp/reload')
      setMsg('✓ ' + t('mcp.reconnected'))
      await loadAll({ silent: true })
      notifyChange('mcp')
      setTimeout(() => setMsg(null), 3000)
    } catch (e) {
      setMsg(t('mcp.reconnect_err') + (errorMessage(e)))
    } finally {
      setReconnecting(false)
    }
  }

  function copy(text, id) {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(''), 2000)
  }

  const totalTools = () => status()?.total_tools || 0
  const connectedCount = () => servers().filter(s => s.connected).length
  const warningCount = () => servers().filter(s => s.enabled && !s.connected).length

  return (
    <div class="panel-page">
      <div class="panel-page-header">
        <div>
          <div style="display:flex;align-items:center;gap:9px"><div class="panel-page-title">MCP Tools</div><InfoButton title="MCP Tools" intro={t('info.mcp.intro')} tip={t('info.mcp.tip')} items={[
            { h: t('info.mcp.1h'), d: t('info.mcp.1d') },
            { h: t('info.mcp.2h'), d: t('info.mcp.2d') },
            { h: t('info.mcp.3h'), d: t('info.mcp.3d') },
            { h: t('info.mcp.4h'), d: t('info.mcp.4d') },
          ]} /></div>
          <div class="panel-page-sub">{t('ui2.mcp_connect')}</div>
        </div>
        <button class="btn btn-primary" onClick={reconnect} disabled={reconnecting()}>
          {reconnecting() ? <span class="spin" /> : t('mcp.reconnect')}
        </button>
      </div>

      {/* KPIs */}
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">{t('mcp.tools_kpi')}</div>
          <div class="kpi-val" style="color:var(--blue)">{totalTools()}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">{t('common.connected')}</div>
          <div class="kpi-val" style="color:var(--green)">{connectedCount()}</div>
        </div>
        <Show when={warningCount() > 0}>
          <div class="kpi-card">
            <div class="kpi-label">{t('ui2.with_warning')}</div>
            <div class="kpi-val" style="color:var(--amber, #f59e0b)">{warningCount()}</div>
          </div>
        </Show>
        <div class="kpi-card">
          <div class="kpi-label">{t('mcp.configured')}</div>
          <div class="kpi-val" style="color:var(--text-2)">{servers().length}</div>
        </div>
      </div>

      <Show when={msg()}>
        <div class={`banner ${msg().startsWith('Error') ? 'banner-error' : msg().startsWith('✓') ? 'banner-ok' : 'banner-warn'}`}>
          {msg()}
        </div>
      </Show>

      {/* Aviso de runtime faltante: es la causa más común de que NINGÚN
          servidor conecte, y sin decirlo el usuario no puede resolverlo. */}
      <Show when={diag() && Object.values(diag().runtimes || {}).some(r => !r.available)}>
        <div class="banner banner-warn" style="font-size:var(--fs-sm);line-height:1.6">
          <div style="font-weight:600;margin-bottom:4px">{t('mcp.runtime_missing')}</div>
          <For each={Object.values(diag().runtimes || {}).filter(r => !r.available)}>{r => (
            <div style="margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <code style="font-family:var(--mono);font-size:var(--fs-xs)">{r.tool}</code>
              <Show when={r.tool === 'uvx'}
                    fallback={<span style="font-size:var(--fs-xs);color:var(--text-3)">{r.install_hint}</span>}>
                <button class="btn btn-glass" style="font-size:var(--fs-xs);padding:3px 10px"
                        disabled={installing() === 'uv'}
                        onClick={() => installRuntime('uv')}>
                  {installing() === 'uv' ? t('mcp.installing_short') : t('mcp.install_now')}
                </button>
              </Show>
            </div>
          )}</For>
        </div>
      </Show>

      {/* Lista de servidores */}
      <Show when={!loading()} fallback={<div style="text-align:center;padding:40px"><span class="spin" /></div>}>
        <Show when={servers().length > 0} fallback={
          <div class="card" style="text-align:center;padding:36px">
            <div style="font-size:36px;opacity:0.25;margin-bottom:14px">⬡</div>
            <div style="font-size:var(--fs-md);font-weight:600;margin-bottom:6px">{t('ui2.no_servers')}</div>
            <div style="font-size:var(--fs-base);color:var(--text-3)">{t('ui2.check_mcp_yaml')}</div>
          </div>
        }>
          <For each={servers()}>
            {(srv) => {
              const meta = SERVER_META[srv.id] || { icon: () => _ic(<circle cx="12" cy="12" r="9"/>), color: '#5b9cf6' }
              const _nk = `mcps.${srv.id}.label`; const _nv = t(_nk); const name = _nv !== _nk ? _nv : (srv.label || srv.id)
              const install = srv.install || ''
              const needsKey = (srv.requires_key || []).length > 0
              const missingKeys = () => (srv.requires_key || []).filter(k => !(srv.keys_status || {})[k])
              const allKeysSet = () => needsKey && missingKeys().length === 0
              return (
                <div class="card fade-up" style={`border-color:${srv.connected ? 'rgba(52,211,153,0.25)' : 'var(--glass-border)'}`}>
                  <div style="display:flex;align-items:flex-start;gap:14px">
                    <div class="app-icon" style={`width:48px;height:48px;flex-shrink:0`}>
                      {meta.icon()}
                    </div>
                    <div style="flex:1;min-width:0">
                      <div style="display:flex;align-items:center;gap:10px;margin-bottom:3px;flex-wrap:wrap">
                        <span style="font-size:var(--fs-md);font-weight:700">{name}</span>
                        <Show when={srv.connected}>
                          <span style="font-size:var(--fs-micro);font-weight:700;padding:2px 8px;border-radius:6px;background:rgba(52,211,153,0.15);color:var(--green)">
                            {t('mcp.connected_n')} · {srv.tool_count} tools
                          </span>
                        </Show>
                        <Show when={srv.enabled && !srv.connected}>
                          <span style="font-size:var(--fs-micro);font-weight:700;padding:2px 8px;border-radius:6px;background:rgba(251,191,36,0.15);color:var(--amber)">
                            {t('mcp.enabled_not_connected')}
                          </span>
                        </Show>
                        <Show when={needsKey}>
                          <span style={`font-size:var(--fs-micro);font-weight:700;padding:2px 8px;border-radius:6px;${allKeysSet() ? 'background:rgba(52,211,153,0.15);color:var(--green)' : 'background:var(--inset-surface);color:var(--text-3)'}`}
                                title={`${t('mcp.requires')}: ${(srv.requires_key||[]).join(', ')}`}>
                            {allKeysSet() ? t('mcp.key_set') : t('mcp.needs_key')}
                          </span>
                        </Show>
                        <Show when={srv.runtime}>
                          <span style="font-size:var(--fs-micro);font-weight:600;padding:2px 8px;border-radius:6px;background:var(--inset-surface);color:var(--text-3)">
                            {srv.runtime === 'python' ? 'Python · uvx' : 'Node · npx'}
                          </span>
                        </Show>
                      </div>
                      <div style="font-size:var(--fs-sm);color:var(--text-3);margin-bottom:12px">{(() => { const k=`mcps.${srv.id}.desc`; const v=t(k); return v!==k?v:(srv.description||name) })()}</div>

                      <Show when={srv.tools && srv.tools.length > 0}>
                        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px">
                          <For each={srv.tools.slice(0, 8)}>
                            {(t) => <span style="font-size:var(--fs-micro);font-family:var(--mono);padding:3px 8px;border-radius:6px;background:var(--inset-surface);color:var(--text-3)">{t}</span>}
                          </For>
                        </div>
                      </Show>

                      <Show when={srv.error && srv.enabled && !srv.connected}>
                        <div style="background:rgba(248,113,113,0.10);border:1px solid rgba(248,113,113,0.25);border-radius:10px;padding:8px 11px;margin-bottom:10px;font-size:var(--fs-xs);color:var(--text-2);line-height:1.5">
                          <strong style="color:#f87171">{t('mcp.why_failed')}:</strong> {srv.error}
                        </div>
                      </Show>

                      <Show when={needsKey}>
                        <div style="background:var(--inset-surface);border-radius:10px;padding:10px 12px;margin-bottom:10px">
                          <div style="font-size:var(--fs-xs);color:var(--text-3);margin-bottom:8px;line-height:1.5">
                            {t('mcp.key_help')}
                            <Show when={srv.risk === 'high'}>
                              <span class="mcp-badge mcp-badge-risk">{t('mcp.risk_high')}</span>
                            </Show>
                            <Show when={srv.setup === 'manual'}>
                              <span class="mcp-badge">{t('mcp.manual_setup')}</span>
                            </Show>
                            <Show when={srv.docs}>
                              {' '}<a href={srv.docs} target="_blank" rel="noreferrer"
                                     style="color:var(--accent);text-decoration:none">{t('mcp.get_key')} →</a>
                            </Show>
                          </div>
                          <For each={srv.requires_key || []}>{(k) => (
                            <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
                              <code style="font-family:var(--mono);font-size:var(--fs-micro);color:var(--text-3);min-width:120px;flex-shrink:0">{k}</code>
                              <Show when={(srv.keys_status||{})[k]}
                                    fallback={
                                <>
                                  <input aria-label={t('mcp.key_ph')} type="password" placeholder={t('mcp.key_ph')}
                                         value={keyDraft()[k] || ''}
                                         onInput={e => setKeyDraft({ ...keyDraft(), [k]: e.target.value })}
                                         style="flex:1;min-width:0;background:var(--bg-2);border:1px solid var(--glass-border);border-radius:6px;padding:5px 9px;font-size:var(--fs-xs);color:var(--text-1)" />
                                  <button class="btn btn-glass" style="font-size:var(--fs-xs);padding:4px 10px"
                                          onClick={() => saveKey(k)}>{t('mcp.key_save')}</button>
                                </>
                              }>
                                <span style="flex:1;font-size:var(--fs-xs);color:var(--green)">✓ {t('mcp.key_configured')}</span>
                                <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:4px 9px"
                                        onClick={() => removeKey(k)}>{t('mcp.key_remove')}</button>
                              </Show>
                            </div>
                          )}</For>
                        </div>
                      </Show>

                      {/* Comando de instalación */}
                      <Show when={!srv.connected && install}>
                        <div style="display:flex;align-items:center;gap:8px;background:var(--inset-surface);border-radius:10px;padding:8px 12px;margin-bottom:10px">
                          <code style="flex:1;font-family:var(--mono);font-size:var(--fs-xs);color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{install}</code>
                          <button onClick={() => copy(install, srv.id)} style="font-size:var(--fs-micro);color:var(--text-3);background:none;border:none;cursor:pointer;white-space:nowrap">
                            {copied() === srv.id ? '✓' : '⎘'}
                          </button>
                        </div>
                      </Show>

                      {/* Toggle */}
                      <button
                        onClick={() => toggle(srv.id, srv.enabled)}
                        disabled={busy() === srv.id}
                        class={srv.enabled ? 'btn btn-danger' : 'btn btn-primary'}
                        style="font-size:var(--fs-sm)"
                      >
                        {busy() === srv.id ? <span class="spin" /> : (srv.enabled ? t('mcp.deactivate') : t('mcp.activate'))}
                      </button>
                    </div>
                  </div>
                </div>
              )
            }}
          </For>
        </Show>
      </Show>

      <div class="banner banner-warn" style="margin-top:16px">
        <span style="font-size:var(--fs-base)">💡</span>
        <div style="font-size:var(--fs-sm)">
          Pulsa <strong>{t('btn.enable')}</strong> y Andromeda conecta el servidor solo (la primera vez descarga lo necesario con npx/uvx; ten Node y uv instalados). No hace falta nada más.
        </div>
      </div>
    </div>
  )
}
