/**
 * MCPPanel.jsx — Gestión de servidores MCP iOS 26.
 * Activar/desactivar servidores, ver herramientas, reconectar.
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
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

  onMount(loadAll)

  async function loadAll() {
    setLoading(true)
    const [srv, st] = await Promise.allSettled([
      axios.get('/api/mcp/servers').then(r => r.data),
      axios.get('/api/mcp/status').then(r => r.data),
    ])
    if (srv.status === 'fulfilled') setServers(srv.value.servers || [])
    if (st.status === 'fulfilled')  setStatus(st.value)
    setLoading(false)
  }

  async function toggle(id, enabled) {
    setBusy(id)
    setMsg(!enabled ? t('mcp.connecting_first') : null)
    try {
      const r = await axios.put(`/api/mcp/servers/${id}`, { enabled: !enabled })
      setMsg((r.data.connected ? '✓ ' : '') + (r.data.message || t('mcp.done')))
      await loadAll()
      setTimeout(() => setMsg(null), 5000)
    } catch (e) {
      setMsg('Error: ' + (e.response?.data?.message || e.message))
    } finally {
      setBusy(null)
    }
  }

  async function reconnect() {
    setReconnecting(true)
    setMsg(null)
    try {
      await axios.post('/api/mcp/reload')
      setMsg('✓ Servidores reconectados')
      await loadAll()
      setTimeout(() => setMsg(null), 3000)
    } catch (e) {
      setMsg(t('mcp.reconnect_err') + (e.response?.data?.message || e.message))
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

      {/* Lista de servidores */}
      <Show when={!loading()} fallback={<div style="text-align:center;padding:40px"><span class="spin" /></div>}>
        <Show when={servers().length > 0} fallback={
          <div class="card" style="text-align:center;padding:36px">
            <div style="font-size:36px;opacity:0.25;margin-bottom:14px">⬡</div>
            <div style="font-size:15px;font-weight:600;margin-bottom:6px">{t('ui2.no_servers')}</div>
            <div style="font-size:13px;color:var(--text-3)">{t('ui2.check_mcp_yaml')}</div>
          </div>
        }>
          <For each={servers()}>
            {(srv) => {
              const meta = SERVER_META[srv.id] || { icon: () => _ic(<circle cx="12" cy="12" r="9"/>), color: '#5b9cf6' }
              const _nk = `mcps.${srv.id}.label`; const _nv = t(_nk); const name = _nv !== _nk ? _nv : (srv.label || srv.id)
              const install = srv.install || ''
              const needsKey = (srv.requires_key || []).length > 0
              return (
                <div class="card fade-up" style={`border-color:${srv.connected ? 'rgba(52,211,153,0.25)' : 'var(--glass-border)'}`}>
                  <div style="display:flex;align-items:flex-start;gap:14px">
                    <div class="app-icon" style={`width:48px;height:48px;flex-shrink:0`}>
                      {meta.icon()}
                    </div>
                    <div style="flex:1;min-width:0">
                      <div style="display:flex;align-items:center;gap:10px;margin-bottom:3px;flex-wrap:wrap">
                        <span style="font-size:15px;font-weight:700">{name}</span>
                        <Show when={srv.connected}>
                          <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:7px;background:rgba(52,211,153,0.15);color:var(--green)">
                            {t('mcp.connected_n')} · {srv.tool_count} tools
                          </span>
                        </Show>
                        <Show when={srv.enabled && !srv.connected}>
                          <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:7px;background:rgba(251,191,36,0.15);color:var(--amber)">
                            ACTIVADO (sin conectar)
                          </span>
                        </Show>
                        <Show when={needsKey}>
                          <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:7px;background:var(--inset-surface);color:var(--text-3)" title={`Requiere: ${(srv.requires_key||[]).join(', ')}`}>
                            REQUIERE API KEY
                          </span>
                        </Show>
                        <Show when={srv.runtime}>
                          <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:7px;background:var(--inset-surface);color:var(--text-3)">
                            {srv.runtime === 'python' ? 'Python · uvx' : 'Node · npx'}
                          </span>
                        </Show>
                      </div>
                      <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">{(() => { const k=`mcps.${srv.id}.desc`; const v=t(k); return v!==k?v:(srv.description||name) })()}</div>

                      <Show when={srv.tools && srv.tools.length > 0}>
                        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px">
                          <For each={srv.tools.slice(0, 8)}>
                            {(t) => <span style="font-size:10px;font-family:var(--mono);padding:3px 8px;border-radius:7px;background:var(--inset-surface);color:var(--text-3)">{t}</span>}
                          </For>
                        </div>
                      </Show>

                      <Show when={needsKey && !srv.connected}>
                        <div style="font-size:11px;color:var(--text-3);margin-bottom:10px;line-height:1.5">
                          Define {(srv.requires_key||[]).map(k => <code style="font-family:var(--mono);background:var(--inset-surface);padding:1px 6px;border-radius:5px;margin:0 2px">{k}</code>)} como variable de entorno antes de abrir Andromeda.
                        </div>
                      </Show>

                      {/* Comando de instalación */}
                      <Show when={!srv.connected && install}>
                        <div style="display:flex;align-items:center;gap:8px;background:var(--inset-surface);border-radius:10px;padding:8px 12px;margin-bottom:10px">
                          <code style="flex:1;font-family:var(--mono);font-size:11px;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{install}</code>
                          <button onClick={() => copy(install, srv.id)} style="font-size:10px;color:var(--text-3);background:none;border:none;cursor:pointer;white-space:nowrap">
                            {copied() === srv.id ? '✓' : '⎘'}
                          </button>
                        </div>
                      </Show>

                      {/* Toggle */}
                      <button
                        onClick={() => toggle(srv.id, srv.enabled)}
                        disabled={busy() === srv.id}
                        class={srv.enabled ? 'btn btn-danger' : 'btn btn-primary'}
                        style="font-size:12px"
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
        <span style="font-size:14px">💡</span>
        <div style="font-size:12px">
          Pulsa <strong>{t('btn.enable')}</strong> y Andromeda conecta el servidor solo (la primera vez descarga lo necesario con npx/uvx; ten Node y uv instalados). No hace falta nada más.
        </div>
      </div>
    </div>
  )
}
