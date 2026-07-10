/**
 * TopBar.jsx — Barra superior minimalista estilo Claude Pro.
 */
import { Show, createSignal } from 'solid-js'
import { health } from '../stores/hardware.js'
import SystemStatus from './SystemStatus.jsx'
import { t } from '../stores/i18n.js'

const TITLES = {
  chat: 'Chat', chatlist: 'Chats', stats: 'Estadísticas', mcp: 'MCP Tools', projects: 'Proyectos', artifacts: 'Artefactos',
  models: 'Modelos de IA', settings: 'Configuración',
}

const TIcon = (props) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{props.children}</svg>
)

export default function TopBar(props) {
  const ollamaOnline = () => health()?.ollama?.reachable
  const [showSystem, setShowSystem] = createSignal(false)
  const [sysClosing, setSysClosing] = createSignal(false)
  function closeSystem() {
    if (sysClosing()) return
    setSysClosing(true)
    setTimeout(() => { setShowSystem(false); setSysClosing(false) }, 200)
  }

  return (
    <header
      style={{
        height: '54px',
        display: 'flex',
        'align-items': 'center',
        gap: '14px',
        padding: '0 18px',
        'border-bottom': '1px solid var(--glass-border)',
        background: 'var(--glass)',
        'backdrop-filter': 'blur(20px) saturate(160%)',
        '-webkit-backdrop-filter': 'blur(20px) saturate(160%)',
        'flex-shrink': 0,
      }}
    >
      {/* Toggle sidebar */}
      <button
        onClick={() => props.setSidebarOpen(v => !v)}
        style="width:34px;height:34px;border-radius:9px;background:transparent;border:none;color:var(--text-3);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s"
        onMouseEnter={e => { e.currentTarget.style.background='var(--hover-surface)'; e.currentTarget.style.color='var(--text-1)' }}
        onMouseLeave={e => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--text-3)' }}
        title={props.sidebarOpen() ? 'Ocultar barra' : 'Mostrar barra'}
      >
        <TIcon><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></TIcon>
      </button>

      <div style="font-size:15px;font-weight:600;letter-spacing:-0.01em">{TITLES[props.activeTab()] || ''}</div>

      <div style="flex:1" />

      {/* Estado Ollama — discreto */}
      <div style={`display:flex;align-items:center;gap:6px;font-size:12px;color:${ollamaOnline()?'var(--text-3)':'var(--amber)'}`}>
        <span style={`width:6px;height:6px;border-radius:50%;background:${ollamaOnline()?'var(--green)':'var(--amber)'}`} />
        {ollamaOnline() ? 'Ollama' : 'Sin conexión'}
      </div>

      {/* Incógnito */}
      <button
        onClick={() => props.setIncognito(v => !v)}
        style={`display:flex;align-items:center;gap:7px;padding:6px 12px;border-radius:9px;border:none;cursor:pointer;font-size:12px;font-weight:500;transition:all 0.15s;background:${props.incognito()?'rgba(154,154,158,0.18)':'transparent'};color:${props.incognito()?'var(--text-1)':'var(--text-3)'}`}
        onMouseEnter={e => { if(!props.incognito()) e.currentTarget.style.background='var(--hover-surface)' }}
        onMouseLeave={e => { if(!props.incognito()) e.currentTarget.style.background='transparent' }}
      >
        <TIcon><path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/></TIcon>
        {t('top.incognito')}
      </button>

      {/* Sistema */}
      <button
        onClick={() => setShowSystem(true)}
        style="display:flex;align-items:center;gap:7px;padding:6px 12px;border-radius:9px;border:none;background:transparent;color:var(--text-3);cursor:pointer;font-size:12px;font-weight:500;transition:all 0.15s"
        onMouseEnter={e => { e.currentTarget.style.background='var(--hover-surface)'; e.currentTarget.style.color='var(--text-1)' }}
        onMouseLeave={e => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--text-3)' }}
      >
        <TIcon><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></TIcon>
        {t('top.system')}
      </button>

      <Show when={showSystem()}>
        <SystemStatus onClose={closeSystem} closing={sysClosing()} />
      </Show>
    </header>
  )
}
