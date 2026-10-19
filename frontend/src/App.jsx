import { orbsOn, design, effectiveBgStyle, accent, ACCENTS, waveCount, waveHeight, animationsOn, compactMode, theme, orbPalette, orbSpeed, orbIntensity, orbSize, orbCustom, orbColors, hydrateFromBackend } from './stores/settings'
import { createSignal, onMount, onCleanup, createEffect, Show, lazy, Suspense } from 'solid-js'
import axios from 'axios'

import TitleBar      from './components/TitleBar.jsx'
import Login         from './components/Login.jsx'
import { session, authRequired, authChecked, checkAuth, showLogin, setShowLogin } from './stores/auth'
import Sidebar       from './components/Sidebar.jsx'
import TopBar        from './components/TopBar.jsx'
import Chat          from './components/Chat.jsx'
// Carga diferida de los paneles pesados: al abrir Andromeda se cargaba TODO
// (analíticas con sus gráficos, laboratorio, explorador de modelos) aunque el
// usuario solo fuera a chatear. Cada panel se descarga la primera vez que se
// abre, no antes.
const StatsPanel     = lazy(() => import('./components/StatsPanel.jsx'))
const AnalyticsPanel = lazy(() => import('./components/AnalyticsPanel.jsx'))
const LabPanel       = lazy(() => import('./components/LabPanel.jsx'))
const SettingsPanel  = lazy(() => import('./components/SettingsPanel.jsx'))
const ProjectsPanel  = lazy(() => import('./components/ProjectsPanel.jsx'))
const ArtifactsPanel = lazy(() => import('./components/ArtifactsPanel.jsx'))
const Codex          = lazy(() => import('./components/Codex.jsx'))
const ChatsListPanel = lazy(() => import('./components/ChatsListPanel.jsx'))
const DiagnosticsPanel = lazy(() => import('./components/DiagnosticsPanel.jsx'))
const FilePreview = lazy(() => import('./components/FilePreview.jsx'))
import Onboarding     from './components/Onboarding.jsx'
import { refreshHardware } from './stores/hardware.js'
import { loadEdition, isPro as isProEd, analyticsAvailable as analyticsAvail, checkDiagnostics } from './stores/edition.js'
import { lang, setLang, hydrateLangFromBackend } from './stores/i18n.js'
import { hydrateConversationsFromBackend, newConversation } from './stores/chat.js'
import { closePreview } from './stores/preview.js'

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
    // Diseño 1.1 (inspirado en macOS), en claro u oscuro
    document.body.classList.toggle('design-11', design() === '1.1')
    document.body.classList.remove('theme-macos')
    // Color de acento del 1.1 (variables que usan selección, burbujas y botones)
    const ac = ACCENTS.find(a => a.id === accent()) || ACCENTS[0]
    const b = document.body.style
    if (design() === '1.1') {
      b.setProperty('--accent', ac.color)
      b.setProperty('--accent-fill', ac.fill || ac.color)
      b.setProperty('--blue', ac.color)
    } else {
      b.removeProperty('--accent'); b.removeProperty('--accent-fill'); b.removeProperty('--blue')
    }
    // Sobre amarillo o verde claros el texto blanco no se lee
    document.body.classList.toggle('accent-light', ['yellow', 'green'].includes(ac.id))
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

  // ¿Debe mostrarse el panel de diagnóstico? Actualiza una señal reactiva, así
  // el menú se entera cuando llega la respuesta (una variable global no basta:
  // el menú ya se ha renderizado para entonces).
  onMount(() => { checkDiagnostics() })

  // Rendimiento: en Windows, efectos de cristal más ligeros (WebView2 sufre más
  // con desenfoques grandes), y en todos los sistemas las animaciones de fondo
  // se pausan cuando la ventana no está visible.
  onMount(() => {
    document.body.classList.toggle('os-win', /Windows/i.test(navigator.userAgent))
    const vis = () => document.body.classList.toggle('app-hidden', document.hidden)
    document.addEventListener('visibilitychange', vis)
    onCleanup(() => document.removeEventListener('visibilitychange', vis))
  })

  // Abrir Configuración cierra la vista previa: si no, el archivo quedaba
  // encima tapando la ventana de ajustes.
  createEffect(() => { if (settingsOpen()) closePreview() })

  // "Usar" un prompt desde Configuración: cerrar ajustes e ir al chat.
  onMount(() => {
    const ir = () => { closeSettings(); setActiveTab('chat') }
    window.addEventListener('andromeda:go-chat', ir)
    onCleanup(() => window.removeEventListener('andromeda:go-chat', ir))
  })

  // Enlaces externos → navegador del sistema. En la app de escritorio se
  // abrían dentro de la propia ventana, sin forma de volver atrás.
  onMount(() => {
    const esEscritorio = /pywebview/i.test(navigator.userAgent) || window.pywebview != null
                         || window.__ANDROMEDA_DESKTOP__ === true
    const alClic = (e) => {
      const a = e.target?.closest?.('a[href]')
      if (!a) return
      const href = a.getAttribute('href') || ''
      if (!/^https?:\/\//i.test(href)) return
      if (new URL(href, location.href).origin === location.origin) return
      e.preventDefault()
      if (esEscritorio) {
        fetch('/api/system/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ url: href }) }).catch(() => {})
      } else {
        window.open(href, '_blank', 'noopener,noreferrer')
      }
    }
    document.addEventListener('click', alClic, true)
    onCleanup(() => document.removeEventListener('click', alClic, true))
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
      <Show when={orbsOn() && effectiveBgStyle() === 'bands'}><div class="bg-bands">
        <div class="bg-band bg-band-1" />
        <div class="bg-band bg-band-2" />
        <div class="bg-band bg-band-3" />
      </div></Show>
      <Show when={orbsOn() && effectiveBgStyle() === 'orbs'}><div class="bg-orbs">
        <div class="bg-orb bg-orb-1" />
        <div class="bg-orb bg-orb-2" />
        <div class="bg-orb bg-orb-3" />
      </div></Show>
      <Show when={orbsOn() && effectiveBgStyle() === 'waves'}><div class="bg-waves" data-count={waveCount()} style={`--wave-h:${waveHeight()}%`}>
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
              {/* Suspense: los paneles se cargan bajo demanda, así que hace
                  falta algo que mostrar durante esa fracción de segundo. */}
              <Suspense fallback={
                <div style="display:flex;align-items:center;justify-content:center;height:100%">
                  <span class="spin" />
                </div>
              }>
              <Show when={activeTab() === 'chat'}>     <div class="page-enter" style="height:100%"><Chat incognito={incognito} onOpenModels={(sec) => openSettings(sec || 'models')} /></div></Show>
              <Show when={activeTab() === 'chatlist'}> <div class="page-enter" style="height:100%"><ChatsListPanel onOpen={() => setActiveTab('chat')} /></div></Show>
              <Show when={activeTab() === 'projects'}> <div class="page-enter" style="height:100%"><ProjectsPanel onNewChat={(pid) => { newConversation(pid); setActiveTab('chat') }} onOpenChat={() => setActiveTab('chat')} /></div></Show>
              <Show when={activeTab() === 'artifacts'}><div class="page-enter" style="height:100%"><ArtifactsPanel /></div></Show>
              <Show when={activeTab() === 'codex'}>    <div class="page-enter" style="height:100%;overflow-y:auto"><Codex /></div></Show>
              <Show when={activeTab() === 'lab' && isProEd()}>     <div class="page-enter" style="height:100%;overflow-y:auto"><LabPanel /></div></Show>
              <Show when={activeTab() === 'stats' && isProEd()}>   <div class="page-enter" style="height:100%;overflow-y:auto"><StatsPanel /></div></Show>
              <Show when={activeTab() === 'analytics' && analyticsAvail()}>   <div class="page-enter" style="height:100%;overflow-y:auto"><AnalyticsPanel /></div></Show>
              <Show when={activeTab() === 'diagnostics'}>  <div class="page-enter" style="height:100%;overflow-y:auto"><DiagnosticsPanel /></div></Show>
              </Suspense>
            </div>
          </div>
        </div>

        {/* Configuración como overlay (estilo Claude): cubre la app y blurea el fondo */}
        {/* Panel lateral de vista previa, a nivel raíz. Antes estaba dentro de
            la ventana de Configuración: solo existía con ella abierta, así que
            en Artefactos no se abría nada y al abrir Configuración aparecía
            el archivo tapándola. */}
        <Suspense fallback={null}><FilePreview /></Suspense>

        <Show when={settingsOpen()}>
          <div class={`cfg-overlay${settingsClosing() ? ' closing' : ''}`} onClick={(e) => { if (e.target === e.currentTarget) closeSettings() }}>
            <div class={`cfg-modal${settingsClosing() ? ' closing' : ''}`}>
              <button class="cfg-close" title="Cerrar" onClick={closeSettings}>
                <svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 2 L14 14 M14 2 L2 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              </button>
              <Suspense fallback={<div style="display:flex;align-items:center;justify-content:center;height:100%"><span class="spin" /></div>}>
                <SettingsPanel initialSection={settingsSection()} />
              </Suspense>
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
