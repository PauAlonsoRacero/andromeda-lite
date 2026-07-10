import { orbsOn, bgStyle, waveCount, waveHeight, animationsOn, compactMode, theme, orbPalette, orbSpeed, orbIntensity, orbSize, orbCustom, orbColors, hydrateFromBackend } from './stores/settings'
import { createSignal, onMount, onCleanup, createEffect, Show } from 'solid-js'
import axios from 'axios'

import TitleBar      from './components/TitleBar.jsx'
import Login         from './components/Login.jsx'
import { session, authRequired, authChecked, checkAuth, showLogin, setShowLogin } from './stores/auth'
import Sidebar       from './components/Sidebar.jsx'
import TopBar        from './components/TopBar.jsx'
import Chat          from './components/Chat.jsx'
import StatsPanel     from './components/StatsPanel.jsx'
import AnalyticsPanel from './components/AnalyticsPanel.jsx'
import LabPanel       from './components/LabPanel.jsx'
import SettingsPanel  from './components/SettingsPanel.jsx'
import ProjectsPanel  from './components/ProjectsPanel.jsx'
import ArtifactsPanel  from './components/ArtifactsPanel.jsx'
import Codex          from './components/Codex.jsx'
import ChatsListPanel from './components/ChatsListPanel.jsx'
import Onboarding     from './components/Onboarding.jsx'
import { refreshHardware } from './stores/hardware.js'
import { loadEdition, isPro as isProEd, analyticsAvailable as analyticsAvail } from './stores/edition.js'
import { lang, setLang, hydrateLangFromBackend } from './stores/i18n.js'
import { hydrateConversationsFromBackend } from './stores/chat.js'

function App() {
  createEffect(() => {
    document.body.classList.toggle('no-anim', !animationsOn())
    document.body.classList.toggle('compact', compactMode())
  })

  // Idioma: aplica el guardado (UI + idioma de las IAs en backend) al arrancar
  createEffect(() => {
    document.documentElement.lang = lang()
  })
  onMount(() => { try { setLang(lang()) } catch {} })

  // Atajos de teclado (calidad de vida):
  //   Esc           → cierra la configuración
  //   Ctrl/Cmd + ,  → abre la configuración (convención del sistema)
  onMount(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && settingsOpen() && !settingsClosing()) {
        closeSettings()
      } else if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        e.preventDefault()
        if (settingsOpen()) closeSettings(); else openSettings('general')
      }
    }
    window.addEventListener('keydown', onKey)
    onCleanup(() => window.removeEventListener('keydown', onKey))
  })

  // Tema claro/oscuro
  createEffect(() => {
    const t = theme() === 'light' ? 'light' : 'dark'
    document.body.classList.toggle('theme-light', t === 'light')
    document.body.classList.toggle('theme-dark', t === 'dark')
  })

  // Paleta de orbes + velocidad + intensidad (variables CSS en :root)
  const ORB_KEYS = ['aurora','ocean','sunset','forest','mono','galaxy']
  // Convierte un hex (#rrggbb) a "r, g, b" para usarlo en rgba()
  const hexToRgb = (hex) => {
    const h = (hex || '').replace('#','')
    const n = parseInt(h.length === 3 ? h.split('').map(c=>c+c).join('') : h, 16)
    return `${(n>>16)&255}, ${(n>>8)&255}, ${n&255}`
  }
  createEffect(() => {
    const p = orbPalette()
    const custom = orbCustom()
    // Si hay colores custom activos, ningún preset de paleta
    ORB_KEYS.forEach(k => document.body.classList.toggle(`orb-${k}`, !custom && k === p))
    document.body.classList.toggle('orb-custom', custom)
    const root = document.documentElement
    root.style.setProperty('--orb-speed', String(orbSpeed()))
    root.style.setProperty('--orb-intensity', String(orbIntensity()))
    root.style.setProperty('--orb-size', String(orbSize()))
    if (custom) {
      const c = orbColors()
      root.style.setProperty('--orb-1', hexToRgb(c[0]))
      root.style.setProperty('--orb-2', hexToRgb(c[1]))
      root.style.setProperty('--orb-3', hexToRgb(c[2]))
    } else {
      root.style.removeProperty('--orb-1')
      root.style.removeProperty('--orb-2')
      root.style.removeProperty('--orb-3')
    }
  })

  const [activeTab, setActiveTab]   = createSignal('chat')
  const [sidebarOpen, setSidebarOpen] = createSignal(true)   // desplegada por defecto
  const [incognito, setIncognito]   = createSignal(false)
  const [settingsOpen, setSettingsOpen] = createSignal(false)
  const [settingsClosing, setSettingsClosing] = createSignal(false)
  const [settingsSection, setSettingsSection] = createSignal('general')
  function openSettings(section = 'general') { setSettingsSection(section); setSettingsOpen(true) }
  // Cierre con animación: marca 'closing', espera a que termine y desmonta.
  function closeSettings() {
    if (settingsClosing()) return
    setSettingsClosing(true)
    setTimeout(() => { setSettingsOpen(false); setSettingsClosing(false) }, 200)
  }

  // Aplicar paleta noir al body cuando se activa incógnito
  createEffect(() => {
    if (typeof document !== 'undefined') {
      document.body.classList.toggle('incognito', incognito())
    }
  })
  const [showOnboarding, setShowOnboarding] = createSignal(false)

  onMount(() => {
    checkAuth()
    refreshHardware()
    loadEdition()
  })

  onMount(async () => {
    // Rehidratar estado persistido en disco (tema, idioma, fondo, conversaciones).
    // En el binario de escritorio localStorage no persiste, así que esta es la
    // fuente fiable. Aplicamos antes de comprobar onboarding.
    await Promise.allSettled([
      hydrateFromBackend(),
      hydrateLangFromBackend(),
      hydrateConversationsFromBackend(),
    ])
    try {
      // Solo mostramos el onboarding en el PRIMER arranque (no si el usuario
      // ya lo completó/saltó antes). Persistido en backend para sobrevivir al
      // reinicio del .exe.
      let alreadyDone = false
      try {
        const u = await axios.get('/api/uistate/onboarding_done')
        alreadyDone = u.data?.value === 'true' || u.data?.value === true
      } catch {}
      if (!alreadyDone) {
        const r = await axios.get('/api/health/setup', { timeout: 8000 })
        // Mostrar onboarding SOLO si falta lo esencial: Ollama no disponible o
        // sin ningún modelo descargado. La activación de especialistas se hace
        // dentro de la app, así que NO bloqueamos por eso.
        const needsOllama = !r.data.ollama_reachable
        const needsModels = !r.data.models?.some(m => m.installed)
        if (needsOllama || needsModels) setShowOnboarding(true)
      }
    } catch {}
  })

  // Al cerrar el onboarding, recordarlo para no volver a mostrarlo cada arranque.
  const finishOnboarding = async () => {
    setShowOnboarding(false)
    try { await axios.put('/api/uistate/onboarding_done', { value: 'true' }) } catch {}
  }

  return (
    <>
      {/* Fondo animado: orbes flotantes o bandas tricolores, según ajuste */}
      <Show when={orbsOn() && bgStyle() === 'bands'}><div class="bg-bands">
        <div class="bg-band bg-band-1" />
        <div class="bg-band bg-band-2" />
        <div class="bg-band bg-band-3" />
      </div></Show>
      <Show when={orbsOn() && bgStyle() === 'orbs'}><div class="bg-orbs">
        <div class="bg-orb bg-orb-1" />
        <div class="bg-orb bg-orb-2" />
        <div class="bg-orb bg-orb-3" />
      </div></Show>
      <Show when={orbsOn() && bgStyle() === 'waves'}><div class="bg-waves" data-count={waveCount()} style={`--wave-h:${waveHeight()}%`}>
        <div class="bg-wave bg-wave-1" />
        <div class="bg-wave bg-wave-2" />
        <Show when={waveCount() >= 3}><div class="bg-wave bg-wave-3" /></Show>
        <Show when={waveCount() >= 4}><div class="bg-wave bg-wave-4" /></Show>
      </div></Show>

      <Show when={true}>
        <Show when={showOnboarding()}>
          <div style="position:fixed;inset:0;z-index:1000;background:var(--bg-0)">
            <Onboarding onDone={finishOnboarding} />
          </div>
        </Show>

        <div style="display:flex;flex-direction:column;height:100%;position:relative;z-index:1">
        <TitleBar />
        <Show when={authChecked() && ((authRequired() && !session()) || showLogin())}>
          <Login canClose={!authRequired() || !!session()} onClose={() => setShowLogin(false)} />
        </Show>
        <Show when={(!authChecked() || !authRequired() || session()) && !showLogin()}>
        <div style="display:flex;flex:1;min-height:0">
          <div class="enter-stagger enter-1">
            <Sidebar
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              open={sidebarOpen}
              setOpen={setSidebarOpen}
              openSettings={() => setSettingsOpen(true)}
            />
          </div>

          <div style="flex:1;display:flex;flex-direction:column;min-width:0">
            <div class="enter-stagger enter-2">
              <TopBar
                activeTab={activeTab}
                incognito={incognito}
                setIncognito={setIncognito}
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
              />
            </div>

            <div class="enter-stagger enter-3" style="flex:1;overflow:hidden;position:relative">
              <Show when={activeTab() === 'chat'}>     <div class="page-enter" style="height:100%"><Chat incognito={incognito} onOpenModels={() => openSettings('models')} /></div></Show>
              <Show when={activeTab() === 'chatlist'}> <div class="page-enter" style="height:100%"><ChatsListPanel onOpen={() => setActiveTab('chat')} /></div></Show>
              <Show when={activeTab() === 'projects'}> <div class="page-enter" style="height:100%"><ProjectsPanel onNewChat={() => setActiveTab('chat')} onOpenChat={() => setActiveTab('chat')} /></div></Show>
              <Show when={activeTab() === 'artifacts'}><div class="page-enter" style="height:100%"><ArtifactsPanel /></div></Show>
              <Show when={activeTab() === 'codex'}>    <div class="page-enter" style="height:100%;overflow-y:auto"><Codex /></div></Show>
              <Show when={activeTab() === 'lab' && isProEd()}>     <div class="page-enter" style="height:100%;overflow-y:auto"><LabPanel /></div></Show>
              <Show when={activeTab() === 'stats' && isProEd()}>   <div class="page-enter" style="height:100%;overflow-y:auto"><StatsPanel /></div></Show>
              <Show when={activeTab() === 'analytics' && analyticsAvail()}>   <div class="page-enter" style="height:100%;overflow-y:auto"><AnalyticsPanel /></div></Show>
            </div>
          </div>
        </div>

        {/* Configuración como overlay (estilo Claude): cubre la app y blurea el fondo */}
        <Show when={settingsOpen()}>
          <div class={`cfg-overlay${settingsClosing() ? ' closing' : ''}`} onClick={(e) => { if (e.target === e.currentTarget) closeSettings() }}>
            <div class={`cfg-modal${settingsClosing() ? ' closing' : ''}`}>
              <button class="cfg-close" title="Cerrar" onClick={closeSettings}>
                <svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 2 L14 14 M14 2 L2 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              </button>
              <SettingsPanel initialSection={settingsSection()} />
            </div>
          </div>
        </Show>
        </Show>
        </div>
      </Show>
    </>
  )
}

export default App
