import { createSignal, For, Show, createEffect, onCleanup, onMount, createMemo} from 'solid-js'
import axios from 'axios'
import { openStream } from '../services/sse.js'
import {
  chatState, streamContent, addUserMessage, startAssistantMessage, activeProject,
  pendingPrompt, setPendingPrompt, imagenesCompletas,
  appendToken, finalizeMessage, failMessage, clearMessages,
  showPlaceholder, streamPlaceholder,
} from '../stores/chat.js'
import { networkEgress } from '../stores/settings.js'
import { on, SYSTEM_CHANGED } from '../stores/events.js'
import MessageBubble from './MessageBubble.jsx'
import TraceViewer from './TraceViewer.jsx'
import ChatSettings from './ChatSettings.jsx'
import PromptLibrary from './PromptLibrary.jsx'
import ExportButton from './ExportButton.jsx'
import ImageUpload from './ImageUpload.jsx'
import { health } from '../stores/hardware.js'
import { isPro } from '../stores/edition.js'
import { t, lang } from '../stores/i18n.js'

// Pool de sugerencias (traducido). Se eligen 4 al azar por sesión y se
// recalculan si cambia el idioma.
const SUGGESTION_KEYS = Array.from({ length: 30 }, (_, i) => `sug.${i + 1}`)
/** 4 sugerencias al azar, sin repetir las que ya están en pantalla. Barajado
 *  Fisher-Yates: el anterior (sort con Math.random) está sesgado y repetía. */
function pickSuggestions(evitar = []) {
  const pool = SUGGESTION_KEYS.filter(k => !evitar.includes(k))
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool.slice(0, 4)
}


/** Reduce una imagen (data URL) a ~480 px en JPEG para guardarla en el chat. */
function miniatura(dataUrl, max = 960) {
  return new Promise(resolve => {
    try {
      const img = new Image()
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height))
        const c = document.createElement('canvas')
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k)
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
        resolve(c.toDataURL('image/jpeg', 0.8))
      }
      img.onerror = () => resolve(dataUrl)
      img.src = dataUrl
    } catch { resolve(dataUrl) }
  })
}

export default function Chat({ incognito, onOpenModels }) {
  let inputRef, endRef
  // Sugerencias que rotan cada 10 s con un fundido mientras la conversación
  // está vacía (antes eran siempre las mismas).
  const [sugKeys, setSugKeys] = createSignal(pickSuggestions())
  const [sugFading, setSugFading] = createSignal(false)
  const quickPrompts = createMemo(() => { lang(); return sugKeys().map(k => t(k)) })
  onMount(() => {
    const rotar = setInterval(() => {
      if (chatState.messages.length || document.hidden) return
      setSugFading(true)
      setTimeout(() => { setSugKeys(pickSuggestions(sugKeys())); setSugFading(false) }, 320)
    }, 10000)
    onCleanup(() => clearInterval(rotar))
  })
  const [cancelFn, setCancelFn] = createSignal(null)
  const [showCfg, setShowCfg]         = createSignal(false)
  // Cierre animado del panel de potencia: se marca "cerrando" y se desmonta al
  // terminar la animación (antes desaparecía de golpe).
  const [cfgClosing, setCfgClosing]   = createSignal(false)
  const closeCfg = () => {
    if (!showCfg() || cfgClosing()) return
    setCfgClosing(true)
    setTimeout(() => { setShowCfg(false); setCfgClosing(false) }, 380)
  }
  const [showLibrary, setShowLibrary] = createSignal(false)
  const [images, setImages]           = createSignal([])
  const [showImages, setShowImages]   = createSignal(false)
  const [files, setFiles]             = createSignal([])       // {name, text}
  let fileInputRef, folderInputRef
  const [forceModel, setForceModel]   = createSignal('')      // '' = automático
  const [ollamaModels, setOllamaModels] = createSignal([])
  const [chatCfg, setChatCfg]         = createSignal({
    parallel_policy: 'auto', max_parallel: null, specialist_levels: {}
  })

  // Lee archivos seleccionados (archivo suelto o carpeta) como texto y los adjunta.
  // Los binarios grandes se omiten; cada archivo se recorta para no saturar el contexto.
  // Adjuntar archivos o una carpeta. Antes se leía TODO como texto (imágenes y
  // bases de datos incluidas, que llegaban como basura ilegible) y sin límite
  // total: una carpeta grande desbordaba el contexto del modelo.
  const EXT_TEXTO = /\.(txt|md|markdown|html?|css|jsx?|tsx?|json|py|csv|xml|ya?ml|toml|ini|sh|sql|java|c|cpp|h|go|rs|php|rb|vue|svelte|log|tex|rst|env\.example)$/i
  const EXT_IMAGEN = /\.(png|jpe?g|gif|webp|bmp)$/i
  const IGNORAR = /(^|\/)(node_modules|\.git|__pycache__|\.venv|venv|dist|build|\.next|\.cache|\.idea|\.vscode)(\/|$)/
  const MAX_POR_ARCHIVO = 20000
  const MAX_TOTAL = 60000

  async function onPickFiles(fileList) {
    const picked = Array.from(fileList || [])
    const out = []
    const omitidos = []
    let total = files().reduce((n, f) => n + (f.text || '').length, 0)
    for (const f of picked) {
      const nombre = f.webkitRelativePath || f.name
      if (IGNORAR.test(nombre)) continue
      // Imágenes → al modelo de visión, no como texto.
      if (EXT_IMAGEN.test(nombre) && f.size < 8 * 1024 * 1024) {
        const url = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => res(null); r.readAsDataURL(f) })
        if (url) setImages(prev => [...prev, url].slice(0, 3))
        continue
      }
      if (!EXT_TEXTO.test(nombre) || f.size > 2 * 1024 * 1024) { omitidos.push(nombre); continue }
      if (total >= MAX_TOTAL) { omitidos.push(nombre); continue }
      try {
        const texto = (await f.text()).slice(0, Math.min(MAX_POR_ARCHIVO, MAX_TOTAL - total))
        total += texto.length
        out.push({ name: nombre, text: texto })
      } catch { omitidos.push(nombre) }
    }
    if (omitidos.length) {
      out.push({ name: t('chat.files_skipped_name'),
                 text: t('chat.files_skipped') + '\n' + omitidos.slice(0, 60).join('\n') })
    }
    setFiles(prev => [...prev, ...out])
  }


  // Cargar modelos disponibles en Ollama para el selector manual.
  // Se refresca cada 20s para que un modelo recién descargado aparezca solo,
  // sin reiniciar Andromeda (plug & play).
  createEffect(() => {
    const load = () => fetch('/api/models/ollama')
      .then(r => r.json())
      .then(d => setOllamaModels(d.models || []))
      .catch(() => {})
    load()
    const id = setInterval(load, 20000)
    onCleanup(() => clearInterval(id))
  })

  // ── Desplazamiento ────────────────────────────────────────────────────
  // Antes, con CADA token se forzaba un desplazamiento suave hasta el final:
  // mientras escribía era imposible subir a leer. Ahora solo sigue el texto si
  // el usuario está abajo; si sube, se queda donde está y aparece un botón para
  // volver al final.
  let scroller = null
  let pegado = true
  let ultimoLen = 0
  const [verBajar, setVerBajar] = createSignal(false)
  const buscarScroller = (el) => {
    while (el && el !== document.body) {
      const oy = getComputedStyle(el).overflowY
      if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) return el
      el = el.parentElement
    }
    return null
  }
  const alScroll = () => {
    if (!scroller) return
    pegado = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80
    setVerBajar(!pegado)
  }
  const bajar = (suave = true) => {
    if (!scroller) scroller = buscarScroller(endRef)
    if (scroller) scroller.scrollTo({ top: scroller.scrollHeight, behavior: suave ? 'smooth' : 'auto' })
    pegado = true; setVerBajar(false)
  }
  createEffect(() => {
    const n = chatState.messages.length
    streamContent()
    if (!scroller) {
      scroller = buscarScroller(endRef)
      scroller?.addEventListener('scroll', alScroll, { passive: true })
    }
    // Un mensaje nuevo del usuario siempre lleva abajo.
    if (n !== ultimoLen) { ultimoLen = n; pegado = true }
    if (pegado) requestAnimationFrame(() => { if (scroller) scroller.scrollTop = scroller.scrollHeight })
  })
  onCleanup(() => scroller?.removeEventListener('scroll', alScroll))

  // Prompt elegido en Configuración → Biblioteca: se escribe en el campo.
  createEffect(() => {
    const p = pendingPrompt()
    if (!p || !inputRef) return
    inputRef.value = p
    inputRef.style.height = 'auto'
    inputRef.style.height = Math.min(inputRef.scrollHeight, 160) + 'px'
    inputRef.focus()
    setPendingPrompt(null)
  })

  async function send(promptOverride) {
    const prompt = (typeof promptOverride === 'string' ? promptOverride : inputRef?.value || '').trim()
    if (!prompt || chatState.isStreaming) return
    if (inputRef) { inputRef.value = ''; inputRef.style.height = 'auto' }

    // Adjuntar contenido de archivos como contexto antes del prompt del usuario
    const att = files()
    let fullPrompt = prompt
    if (att.length) {
      const blocks = att.map(f => `--- ${f.name} ---\n${f.text}`).join('\n\n')
      fullPrompt = `${t('chat.files_context')}\n\n${blocks}\n\n---\n\n${prompt}`
    }

    // Miniaturas para el historial: las conversaciones se guardan en el
    // almacenamiento local (~5 MB). Una foto de móvil en base64 ocupa 3-5 MB, así
    // que con una o dos el historial dejaba de guardarse sin avisar. Al modelo
    // le llega la imagen completa; aquí solo se conserva una vista reducida.
    const miniaturas = await Promise.all(images().slice(0, 3).map(img => miniatura(img)))
    miniaturas.forEach((m, i) => imagenesCompletas.set(m, images()[i]))
    addUserMessage(prompt, (images().length || att.length) ? {
      images: miniaturas,
      files: att.map(f => ({ name: f.name, size: (f.text || '').length })),
    } : null)
    const reqId = crypto.randomUUID()
    startAssistantMessage(reqId)
    const cfg = chatCfg()
    const cancel = openStream({
      prompt: fullPrompt, strategy: 'auto',
      images: images(),
      incognito: incognito?.() || false,
      parallel_policy: cfg.parallel_policy,
      max_parallel: cfg.max_parallel,
      specialist_levels: cfg.specialist_levels,
      force_model: forceModel() || null,
      // Proyecto de la conversación: instrucciones + memoria del proyecto y su
      // carpeta de archivos. Antes nunca se enviaba y los proyectos no hacían nada.
      ...(() => {
        const pr = activeProject()
        if (!pr) return {}
        const instr = [pr.instructions, pr.memory].filter(x => (x || '').trim()).join('\n\n')
        return { project_id: pr.id, project_name: pr.name, project_instructions: instr }
      })(),
      // El mensaje actual ya se añadió al chat (addUserMessage) y va aparte
      // como `prompt`: si se incluye aquí, el modelo lo recibe dos veces.
      conversation_history: chatState.messages
        // Sin mensajes de error: entraban como respuestas del asistente y el
        // modelo acababa hablando de "un problema con la respuesta anterior".
        .filter(m => !m.streaming && !m.error && m.content && m.role)
        .filter((m, i, arr) => !(i === arr.length - 1 && m.role === 'user' && m.content === prompt))
        .slice(-8)
        .map(m => ({ role: m.role, content: (m.content || '').slice(0, 500) })),
      onToken: (token, specId) => appendToken(token, specId),
      onPlaceholder: (phrase, level) => showPlaceholder(phrase, level),
      onComplete(meta) {
        if (incognito?.()) meta = { ...meta, trace_id: null }
        finalizeMessage(reqId, meta)
        setCancelFn(null)
        // Notificar que la respuesta terminó (según preferencias de alertas)
        try {
          import('./AlertsWidget.jsx').then(m => m.notifyComplete?.(meta?.latency_ms || 0))
        } catch { /* carga de fondo: un fallo puntual no debe molestar al usuario */ }
      },
      onError(err) {
        failMessage(reqId, `⚠️ ${err?.message || t('js.conn_error')}`)
        setCancelFn(null)
      },
    })
    setCancelFn(() => cancel)
    setImages([]); setShowImages(false)
    setFiles([])
  }

  function cancel() {
    cancelFn()?.()
    setCancelFn(null)
    const last = chatState.messages.at(-1)
    if (last?.streaming) finalizeMessage(last.id, { cancelled: true })
  }

  // ── Slash commands: menú de autocompletado al escribir "/" ────────────
  const [slashOpen, setSlashOpen] = createSignal(false)
  const [slashSel, setSlashSel] = createSignal(0)
  const [allCmds, setAllCmds] = createSignal([])
  // Un conector MCP como 'fetch' o 'brave-search' ya da acceso a internet:
  // seguir avisando de que "la búsqueda está desactivada" sería falso.
  const [webViaMcp, setWebViaMcp] = createSignal(false)
  async function checkWebAccess() {
    try {
      const r = await axios.get('/api/mcp/status')
      const servers = r.data?.servers || {}
      const WEB = ['fetch', 'brave-search', 'web-search', 'playwright', 'puppeteer']
      setWebViaMcp(Object.entries(servers).some(
        ([id, s]) => s?.connected && WEB.some(w => id.includes(w))))
    } catch { setWebViaMcp(false) }
  }
  onMount(async () => {
    try { setAllCmds((await axios.get('/api/commands')).data.commands || []) } catch { /* carga de fondo: un fallo puntual no debe molestar al usuario */ }
    checkWebAccess()
  })
  // Reaccionar cuando el usuario active un conector en otra pantalla.
  onCleanup(on(SYSTEM_CHANGED, checkWebAccess))
  // Solo se ofrece mientras se escribe el comando (una palabra tras "/").
  const slashMatches = () => {
    const v = inputRef?.value || ''
    const m = /^\/([a-zA-Z-]*)$/.exec(v)
    if (!m) return []
    const q = m[1].toLowerCase()
    return allCmds().filter(c =>
      c.name.startsWith(q) || (c.aliases || []).some(a => a.startsWith(q))).slice(0, 8)
  }
  function applySlash(cmd) {
    if (!inputRef) return
    inputRef.value = '/' + cmd.name + ' '
    setSlashOpen(false)
    inputRef.focus()
    inputRef.dispatchEvent(new Event('input', { bubbles: true }))
  }

  function onInput(e) {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
    const open = slashMatches().length > 0
    setSlashOpen(open)
    if (open) setSlashSel(0)
  }
  function onKey(e) {
    if (slashOpen()) {
      const list = slashMatches()
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashSel((slashSel() + 1) % list.length); return }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setSlashSel((slashSel() - 1 + list.length) % list.length); return }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault(); applySlash(list[slashSel()]); return
      }
      if (e.key === 'Escape')    { setSlashOpen(false); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const sysOk   = () => health()?.status !== 'down'
  const specOk  = () => health()?.specialists?.active > 0
  const canSend = () => sysOk() && specOk() && !chatState.isStreaming

  const placeholder = () => {
    if (!sysOk())      return t('chat.ph_system_down')
    if (!specOk())     return t('chat.ph_no_ais')
    if (incognito?.()) return t('chat.incognito_active')
    return t('chat.placeholder')
  }

  return (
    <div style="height:100%;display:flex;flex-direction:column;position:relative">
      {/* Mensajes */}
      <div style="flex:1;overflow-y:auto;padding:24px 0">
        <Show
          when={chatState.messages.length > 0}
          fallback={
            <div style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:40px">
              <img class="welcome-logo" src="/andromeda-logo.png" alt="" style="width:72px;height:72px;object-fit:contain;margin-bottom:20px;animation:pulse 3s ease-in-out infinite" />
              <div class="welcome-title" style="font-size:var(--fs-xl);font-weight:800;letter-spacing:-0.02em;margin-bottom:10px">
                {incognito?.() ? t('incognito.title') : 'Andromeda'}
              </div>
              <div class="welcome-sub" style="font-size:var(--fs-base);color:var(--text-3);max-width:440px;line-height:1.6;margin-bottom:28px">
                <Show when={!sysOk()}>
                  <span style="color:var(--red)">{t("chat.sys_down")}</span>
                </Show>
                <Show when={sysOk() && !specOk()}>
                  <Show when={ollamaModels().length === 0} fallback={
                    <>{t("chat.no_ai_pre")}<span style="color:var(--teal)">{t("chat.ai_models")}</span>{t("chat.no_ai_post")}</>
                  }>
                    {t('chat.no_models_installed')}
                  </Show>
                </Show>
                <Show when={sysOk() && specOk()}>
                  <Show when={isPro()} fallback={t('incognito.subtitle')}>
                    {t('chat.pro_subtitle')}
                  </Show>
                </Show>
              </div>

              {/* Onboarding: no hay IA activa → guía de primeros pasos.
                  Se muestra tanto si no hay modelos instalados como si hay
                  pero ninguno está activado todavía. */}
              <Show when={sysOk() && !specOk()}>
                <div style="max-width:520px;width:100%;text-align:left;background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:14px;padding:22px 24px">
                  <div style="font-size:var(--fs-base);font-weight:700;margin-bottom:14px;text-align:center">{t('ui2.first_steps')}</div>
                  <div style="display:flex;flex-direction:column;gap:14px">
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:var(--fs-sm);font-weight:700;flex-shrink:0">1</div>
                      <div style="font-size:var(--fs-base);color:var(--text-2);line-height:1.55">
                        {t('ob.step1_pre')}<span style="color:var(--teal);font-weight:600">{t('ui2.ai_models')}</span>{t('ob.step1_post')}
                      </div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:var(--fs-sm);font-weight:700;flex-shrink:0">2</div>
                      <div style="font-size:var(--fs-base);color:var(--text-2);line-height:1.55">
                        <Show when={ollamaModels().length === 0} fallback={
                          <>{t("chat.tab_pre")}<span style="color:var(--text-1);font-weight:600">{t("chat.specialists")}</span>{t("chat.tab_post")}</>
                        }>
                          {t('ob.step2_pre')}<span style="color:var(--text-1);font-weight:600">{t('ui2.explore_models')}</span>{t('ob.step2_post')}
                        </Show>
                      </div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:var(--fs-sm);font-weight:700;flex-shrink:0">3</div>
                      <div style="font-size:var(--fs-base);color:var(--text-2);line-height:1.55">
                        {t('ob.step3')}
                      </div>
                    </div>
                  </div>
                  <button onClick={() => onOpenModels?.()}
                    class="btn btn-primary" style="width:100%;margin-top:18px"
                    >{t('ui2.go_models')}</button>
                </div>
              </Show>
              <Show when={sysOk() && specOk()}>
                <div class="welcome-chips" classList={{ fading: sugFading() }} style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;max-width:560px">
                  <For each={quickPrompts()}>
                    {(p) => (
                      <button
                        onClick={() => send(p)}
                        class="glass"
                        style="padding:10px 16px;border-radius:var(--r-sm);font-size:var(--fs-base);color:var(--text-2);cursor:pointer;transition:all 0.2s;background:var(--glass);font-family:var(--font)"
                        onMouseEnter={e => { e.currentTarget.style.color='var(--text-1)'; e.currentTarget.style.transform='translateY(-2px)' }}
                        onMouseLeave={e => { e.currentTarget.style.color='var(--text-2)'; e.currentTarget.style.transform='translateY(0)' }}
                      >
                        {p.length > 42 ? p.slice(0,42) + '…' : p}
                      </button>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          }
        >
          {/* Contenedor estrecho centrado tipo Claude */}
          <div style="max-width:760px;margin:0 auto;padding:0 24px">
            <For each={chatState.messages}>
              {(msg) => <MessageBubble message={msg} />}
            </For>
            <Show when={verBajar()}>
              <button class="jump-bottom" onClick={() => bajar()} aria-label={t('chat.jump_bottom')}>↓</button>
            </Show>
            <div ref={endRef} style="height:1px" />
          </div>
        </Show>
      </div>

      {/* Trace viewer — solo en Pro (en Lite siempre es single-IA, no aporta) */}
      <Show when={isPro() && !incognito?.() && chatState.messages.length > 0}>
        <div style="max-width:760px;margin:0 auto;width:100%;padding:0 24px">
          <TraceViewer />
        </div>
      </Show>

      {/* Input estrecho y centrado */}
      <div style="padding:16px 24px 22px">
        <div style="max-width:760px;margin:0 auto">

          {/* Paneles como modales centrados (no fuera de pantalla) */}
          <Show when={showLibrary()}>
            <PromptLibrary
                  onSelect={(content) => {
                    if (inputRef) {
                      inputRef.value = content
                      inputRef.style.height = 'auto'
                      inputRef.style.height = Math.min(inputRef.scrollHeight, 160) + 'px'
                      inputRef.focus()
                    }
                    setShowLibrary(false)
                  }}
                  onClose={() => setShowLibrary(false)}
                />
              </Show>
          <Show when={files().length > 0}>
            <div style="display:flex;flex-wrap:wrap;gap:6px;padding:0 4px 8px">
              <For each={files()}>
                {(f, i) => (
                  <span style="display:inline-flex;align-items:center;gap:6px;font-size:var(--fs-xs);background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:4px 8px;color:var(--text-2);max-width:220px">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{f.name}</span>
                    <button onClick={() => setFiles(prev => prev.filter((_, j) => j !== i()))} style="background:none;border:none;color:var(--text-3);cursor:pointer;padding:0;display:flex" title={t("chat.remove")}>
                      <svg width="12" height="12" viewBox="0 0 16 16"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                    </button>
                  </span>
                )}
              </For>
            </div>
          </Show>
          <Show when={showImages()}>
            <div class="settings-overlay" onClick={() => setShowImages(false)}>
              <div onClick={e => e.stopPropagation()}>
                <div style="font-size:var(--fs-md);font-weight:700;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center">
                  Añadir imágenes
                  <button onClick={() => setShowImages(false)} style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:var(--fs-lg)">✕</button>
                </div>
                <ImageUpload onImages={setImages} />
              </div>
            </div>
          </Show>

          {/* INPUT BAR EXPANDIBLE — se agranda cuando showCfg está activo */}
          <div class="liquid-glass" style={`position:relative;border-radius:26px;padding:12px;transition:all 0.3s cubic-bezier(0.4,0,0.2,1);${showCfg()?'display:flex;flex-direction:column;gap:10px':'padding:8px 8px 8px 10px'}`}>
            {/* Panel de configuración — se muestra dentro cuando showCfg es true */}
            <Show when={showCfg()}>
              {/* Envoltorio que anima la ALTURA: sin él, la caja de mensaje
                  cambiaba de tamaño de golpe y tapaba la animación del panel. */}
              <div class="ias-wrap" classList={{ closing: cfgClosing() }}>
              <div class="ias-expand" classList={{ closing: cfgClosing() }} style="display:flex;flex-direction:column;gap:10px;padding:4px 4px 12px;border-bottom:1px solid var(--glass-border);max-height:54vh;overflow-y:auto">
                <div style="font-size:var(--fs-base);font-weight:700;letter-spacing:-0.01em;display:flex;justify-content:space-between;align-items:center;color:var(--text-1)">
                  {isPro() ? t('chat.cfg_title_pro') : t('chat.power_title')}
                  <button onClick={closeCfg} title={t("chat.close")} style="display:flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:var(--hover-surface);border:1px solid var(--glass-border);color:var(--text-3);cursor:pointer;transition:all .15s">
                    <svg width="13" height="13" viewBox="0 0 16 16"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                  </button>
                </div>
                <Show when={forceModel()}>
                  <div style="font-size:var(--fs-sm);padding:10px 12px;border-radius:14px;background:var(--inset-surface);border:1px solid var(--glass-border);color:var(--text-2);display:flex;justify-content:space-between;align-items:center;gap:10px">
                    <span>{t("chat.forcing_pre")}<b style="color:var(--text-1)">{forceModel()}</b>{t("chat.forcing_post")}</span>
                    <button onClick={() => setForceModel('')} style="background:var(--grad-primary);border:none;color:#fff;cursor:pointer;font-size:var(--fs-xs);font-weight:600;padding:5px 12px;border-radius:10px;white-space:nowrap">{t('ui2.back_auto')}</button>
                  </div>
                </Show>
                <ChatSettings onChange={setChatCfg} forceModel={forceModel()} setForceModel={setForceModel} ollamaModels={ollamaModels()} onApplied={closeCfg} />
              </div>
              </div>
            </Show>

            {/* Indicador de búsqueda web: sin esto, el usuario no descubre que
                existe el interruptor y solo ve a la IA decir "no puedo buscar". */}
            <Show when={!incognito?.() && !networkEgress() && !webViaMcp()}>
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:var(--fs-xs);color:var(--text-3)">
                <span style="opacity:.7">🌐</span>
                <span>{t('chat.web_off_hint')}</span>
                <button onClick={() => onOpenModels?.('capabilities')}
                        style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:var(--fs-xs);padding:0;text-decoration:underline">
                  {t('chat.web_off_cta')}
                </button>
              </div>
            </Show>

            {/* Menú de slash commands */}
            <Show when={slashOpen() && slashMatches().length}>
              <div style="position:absolute;bottom:100%;left:0;right:0;margin-bottom:8px;background:var(--bg-2);border:1px solid var(--glass-border);border-radius:14px;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.35);z-index:40;max-height:280px;overflow-y:auto">
                <For each={slashMatches()}>{(c, i) => (
                  <div onMouseDown={e => { e.preventDefault(); applySlash(c) }}
                       onMouseEnter={() => setSlashSel(i())}
                       style={`display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 14px;cursor:pointer;font-size:var(--fs-base);${i() === slashSel() ? 'background:var(--hover-surface)' : ''}`}>
                    <span style="color:var(--text-1);font-weight:600">/{c.name}</span>
                    <span style="color:var(--text-3);font-size:var(--fs-xs);text-align:right;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{c.description}</span>
                  </div>
                )}</For>
              </div>
            </Show>

            {/* Textarea y botón de envío */}
            <div style={`display:flex;align-items:flex-end;gap:8px;${showCfg()?'flex:1':''}`}>
              <textarea
                ref={inputRef}
                placeholder={placeholder()}
                disabled={!canSend() && !chatState.isStreaming}
                onInput={onInput}
                onKeyDown={onKey}
                rows={1}
                style="flex:1;background:transparent;border:none;outline:none;resize:none;color:var(--text-1);font-family:var(--font);font-size:var(--fs-md);padding:10px 8px;max-height:160px;line-height:1.5"
              />
              <button
                onClick={chatState.isStreaming ? cancel : () => send()}
                disabled={!canSend() && !chatState.isStreaming}
                style={`width:42px;height:42px;border-radius:20px;border:none;cursor:pointer;font-size:var(--fs-lg);display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s;background:${(canSend()||chatState.isStreaming)?'var(--grad-primary)':'rgba(255,255,255,0.08)'};color:${(canSend()||chatState.isStreaming)?'white':'var(--text-3)'};${(canSend()||chatState.isStreaming)?'box-shadow:0 4px 14px rgba(240,164,140,0.35)':''}`}
                title={chatState.isStreaming ? 'Cancelar' : 'Enviar (Enter)'}
              >
                <Show when={chatState.isStreaming} fallback="↑">✕</Show>
              </button>
            </div>
          </div>

          {/* Footer con botones de acción */}
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding:0 6px;gap:10px;flex-wrap:wrap">
            <span style="font-size:var(--fs-xs);color:var(--text-3)">{t("chat.send_hint")}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <ChatActionBtn title={t("chat.prompts")} active={showLibrary()} onClick={() => { setShowLibrary(v=>!v); closeCfg(); setShowImages(false) }}><IconBook /></ChatActionBtn>
              <ChatActionBtn label={images().length ? String(images().length) : ''} title={t("chat.add_images")} active={showImages()} onClick={() => { setShowImages(v=>!v); closeCfg(); setShowLibrary(false) }}><IconImage /></ChatActionBtn>
              {/* Adjuntar archivos / carpetas */}
              <input ref={fileInputRef} type="file" multiple style="display:none" onChange={e => { onPickFiles(e.currentTarget.files); e.currentTarget.value='' }} />
              <input ref={folderInputRef} type="file" attr:webkitdirectory="true" attr:directory="true" multiple style="display:none" onChange={e => { onPickFiles(e.currentTarget.files); e.currentTarget.value='' }} />
              <ChatActionBtn label={files().length ? String(files().length) : ''} title={t("chat.attach_files")}
                active={files().length > 0}
                onClick={() => fileInputRef?.click()}>
                <span onContextMenu={(e) => { e.preventDefault(); folderInputRef?.click() }}><IconPaperclip /></span>
              </ChatActionBtn>
              <Show when={files().length > 0}>
                <ChatActionBtn title={t("chat.attach_folder")} onClick={() => folderInputRef?.click()}><IconFolderPlus /></ChatActionBtn>
              </Show>
              <ChatActionBtn label={isPro() ? 'IAs' : t('chat.power_btn')} title={isPro() ? t('chat.cfg_btn_title_pro') : t('chat.power_btn_title')} active={showCfg()} onClick={() => { showCfg() ? closeCfg() : setShowCfg(true); setShowImages(false); setShowLibrary(false) }}><IconSliders /></ChatActionBtn>
              <Show when={chatState.messages.length > 0 && !chatState.isStreaming}>
                <ExportButton />
              </Show>
              <Show when={specOk() && isPro()}>
                <span style="font-size:var(--fs-xs);color:var(--text-3);display:flex;align-items:center;gap:5px;margin-left:4px">
                  <span style="width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green)" />
                  {health()?.specialists?.active} IA{health()?.specialists?.active !== 1 ? 's' : ''}
                </span>
              </Show>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ChatActionBtn(props) {
  return (
    <button
      onClick={props.onClick}
      title={props.title}
      style={`display:flex;align-items:center;gap:6px;font-size:var(--fs-xs);font-weight:600;padding:6px 11px;border-radius:10px;cursor:pointer;font-family:var(--font);transition:all 0.15s;border:1px solid ${props.active?'var(--glass-border)':'transparent'};background:${props.active?'var(--glass-bright)':'var(--hover-surface)'};color:${props.active?'var(--text-1)':'var(--text-3)'}`}
    >
      {props.children}
      <Show when={props.label}>{props.label}</Show>
    </button>
  )
}

// Iconos de línea coherentes con el resto de Andromeda (stroke currentColor)
function IconBook() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
}
function IconImage() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-4.5-4.5L5 21"/></svg>
}
function IconSliders() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
}
function IconTrash() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
}
function IconPaperclip() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
}
function IconFolderPlus() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
}
