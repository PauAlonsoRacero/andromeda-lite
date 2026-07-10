/**
 * Sidebar.jsx — Barra lateral estilo Claude + Liquid Glass iOS 26.
 * Logo nuevo, fuente elegante, nav con "Nueva conversación" bajo Chats.
 */
import { For, Show, createSignal, onMount } from 'solid-js'
import axios from 'axios'
import { advancedMode, artifactsEnabled } from '../stores/settings'
import { isPro, editionLoaded, analyticsAvailable } from '../stores/edition'
import { hardware, activeSpecialists, health } from '../stores/hardware.js'
import { APP_VERSION_LABEL, APP_BUILD } from '../version.js'
import { t } from '../stores/i18n.js'
import { conversations, activeConvId, loadConversation, newConversation, deleteConversation } from '../stores/chat.js'

const Icon = (props) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">
    {props.children}
  </svg>
)
const IconNew    = () => <Icon><path d="M12 5v14M5 12h14"/></Icon>
const IconProjects = () => <Icon><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></Icon>
const IconArtifacts = () => <Icon><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></Icon>
const IconStats  = () => <Icon><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></Icon>
const IconAnalytics = () => <Icon><path d="M3 3v18h18"/><path d="M19 9l-5 5-4-4-3 3"/></Icon>
const IconCodex  = () => <Icon><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></Icon>
const IconSettings = () => <Icon><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></Icon>

export default function Sidebar(props) {
  const isActive = (id) => props.activeTab() === id
  const go = (id) => props.setActiveTab(id)

  // Comprobación de actualizaciones (no bloqueante, falla en silencio)
  const [update, setUpdate] = createSignal(null)  // {latest, url, notes} | null
  onMount(async () => {
    try {
      const r = await axios.get('/api/updates/check')
      if (r.data?.update_available) setUpdate(r.data)
    } catch {}
  })

  const IconLab   = () => <Icon><circle cx="12" cy="12" r="1"/><circle cx="19" cy="5" r="1"/><circle cx="5" cy="19" r="1"/><line x1="12" y1="13" x2="18" y2="19"/><line x1="12" y1="13" x2="6" y2="19"/><line x1="12" y1="13" x2="19" y2="6"/></Icon>

  const NAV_MAIN = () => [
    { id: '__new',     labelKey: 'nav.new_chat', icon: IconNew, action: () => { newConversation(); go('chat') } },
    { id: 'projects',  labelKey: 'nav.projects',  icon: IconProjects, action: () => go('projects') },
    ...(artifactsEnabled() ? [{ id: 'artifacts', labelKey: 'nav.artifacts', icon: IconArtifacts, action: () => go('artifacts') }] : []),
    { id: 'codex',     labelKey: 'nav.codex',     icon: IconCodex,  action: () => go('codex') },
  ]
  const NAV_ANALYTICS = { id: 'analytics', labelKey: 'nav.analytics', icon: IconAnalytics, action: () => go('analytics') }
  const NAV_SETTINGS  = { id: 'settings',  labelKey: 'nav.settings',  icon: IconSettings, action: () => props.openSettings?.() }

  const NAV_ADVANCED = [
    { id: 'lab',       labelKey: 'nav.lab',    icon: IconLab,    action: () => go('lab') },
    { id: 'stats',     labelKey: 'nav.stats',  icon: IconStats,  action: () => go('stats') },
  ]

  // Orden: principales · (analytics si disponible) · (MLOps avanzado si Pro+modo) · ajustes
  // Lab IA y Estadísticas/MLOps son Pro y requieren modo avanzado.
  const NAV = () => [
    ...NAV_MAIN(),
    ...(analyticsAvailable() ? [NAV_ANALYTICS] : []),
    ...((isPro() && advancedMode()) ? NAV_ADVANCED : []),
    NAV_SETTINGS,
  ]

  return (
      <aside
        class={props.open() ? 'sidebar-anim sidebar-open' : 'sidebar-anim sidebar-closed'}
      >
        {/* Logo + nombre */}
        <div
          style="display:flex;align-items:center;gap:11px;padding:22px 22px 24px"
        >
          <img src="/andromeda-logo.png" alt="Andromeda" style="width:42px;height:42px;object-fit:contain" />
          <span style="font-family:'Playfair Display',Georgia,serif;font-size:26px;font-weight:600;color:var(--text-1);letter-spacing:0.01em">Andromeda</span>
          <Show when={editionLoaded() && isPro()}>
            <span style="font-size:9px;font-weight:800;letter-spacing:0.08em;color:#fff;background:var(--grad-primary);padding:2px 7px;border-radius:6px;text-transform:uppercase">Pro</span>
          </Show>
        </div>

        {/* Navegación */}
        <nav style="padding:0 14px;display:flex;flex-direction:column;gap:2px">
          <For each={NAV()}>
            {(item) => (
              <button
                onClick={item.action}
                style={{
                  display: 'flex', 'align-items': 'center', gap: '14px',
                  padding: '11px 14px', 'border-radius': '14px', border: 'none',
                  background: (item.id !== '__new' && isActive(item.id)) ? 'var(--hover-surface)' : 'transparent',
                  color: (item.id !== '__new' && isActive(item.id)) ? 'var(--text-1)' : 'var(--text-2)',
                  cursor: 'pointer', transition: 'all 0.18s', 'text-align': 'left', width: '100%',
                }}
                onMouseEnter={e => { if(item.id==='__new' || !isActive(item.id)) e.currentTarget.style.background='var(--hover-surface)' }}
                onMouseLeave={e => { if(item.id==='__new' || !isActive(item.id)) e.currentTarget.style.background='transparent' }}
              >
                <item.icon />
                <span style="font-size:15px;font-weight:500">{t(item.labelKey)}</span>
              </button>
            )}
          </For>
        </nav>

        {/* Historial */}
        <div style="flex:1;overflow-y:auto;padding:8px 14px 20px;margin-top:14px">
          <div
            onClick={() => go('chatlist')}
            title={t("side.view_all")}
            style="font-size:12px;font-weight:700;color:var(--text-3);padding:14px 14px 10px;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer;transition:color 0.18s"
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >{t("nav.history")}</div>
          <Show when={conversations().length > 0} fallback={
            <div style="font-size:13px;color:var(--text-3);padding:8px 14px;line-height:1.5">
              Sin conversaciones.
            </div>
          }>
            <div style="display:flex;flex-direction:column;gap:1px">
              <For each={conversations().slice(0, 12)}>
                {(c) => (
                  <div
                    style={{
                      display: 'flex', 'align-items': 'center', 'border-radius': '12px',
                      background: activeConvId() === c.id ? 'var(--hover-surface)' : 'transparent',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { if(activeConvId()!==c.id) e.currentTarget.style.background='var(--hover-surface)'; e.currentTarget.querySelector('.del-btn').style.opacity='1' }}
                    onMouseLeave={e => { if(activeConvId()!==c.id) e.currentTarget.style.background='transparent'; e.currentTarget.querySelector('.del-btn').style.opacity='0' }}
                  >
                    <button onClick={() => { loadConversation(c.id); go('chat') }}
                      style="flex:1;background:none;border:none;cursor:pointer;text-align:left;min-width:0;padding:10px 14px">
                      <span style={`font-size:14px;color:${activeConvId()===c.id?'var(--text-1)':'var(--text-2)'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block`}>
                        {c.title || 'Conversación'}
                      </span>
                    </button>
                    <button class="del-btn" onClick={(e) => { e.stopPropagation(); deleteConversation(c.id) }}
                      style="opacity:0;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:15px;padding:0 12px;transition:opacity 0.15s;flex-shrink:0" title={t("side.delete")}>×</button>
                  </div>
                )}
              </For>
            </div>
          </Show>
        </div>

        {/* Pie: aviso de actualización o versión */}
        <Show
          when={update()}
          fallback={
            <div style="flex-shrink:0;padding:12px 18px;border-top:1px solid var(--hairline);display:flex;align-items:center;gap:8px">
              <span style="width:6px;height:6px;border-radius:50%;background:var(--blue);opacity:0.7" />
              <span style="font-size:11px;color:var(--text-3);font-weight:600;letter-spacing:0.02em">Andromeda {APP_VERSION_LABEL} · build {APP_BUILD}</span>
            </div>
          }
        >
          <a href={update().url} target="_blank" rel="noopener"
            style="flex-shrink:0;margin:10px 14px;padding:11px 14px;border-radius:14px;border:1px solid var(--blue);background:var(--blue-subtle, rgba(91,156,246,.10));display:flex;align-items:center;gap:11px;text-decoration:none;cursor:pointer;transition:all .18s"
            onMouseEnter={e => e.currentTarget.style.background='rgba(91,156,246,.18)'}
            onMouseLeave={e => e.currentTarget.style.background='rgba(91,156,246,.10)'}
            title={`Versión ${update().latest} disponible`}>
            <span class="anim-pulse" style="width:8px;height:8px;border-radius:50%;background:var(--blue);flex-shrink:0" />
            <div style="min-width:0;line-height:1.3">
              <div style="font-size:13px;font-weight:700;color:var(--text-1)">{t("side.update")}</div>
              <div style="font-size:11px;color:var(--text-3)">v{update().latest} · pulsa para descargar</div>
            </div>
          </a>
        </Show>
      </aside>
  )
}
