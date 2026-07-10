import { createSignal, For, Show, createEffect, onCleanup, createMemo} from 'solid-js'
import { openStream } from '../services/sse.js'
import {
  chatState, streamContent, addUserMessage, startAssistantMessage,
  appendToken, finalizeMessage, failMessage, clearMessages,
  showPlaceholder, streamPlaceholder,
} from '../stores/chat.js'
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
const SUGGESTION_KEYS = ['sug.1','sug.2','sug.3','sug.4','sug.5','sug.6','sug.7','sug.8','sug.9','sug.10']
function pickSuggestions() {
  const shuffled = [...SUGGESTION_KEYS].sort(() => Math.random() - 0.5)
  return shuffled.slice(0, 4).map(k => t(k))
}

export default function Chat({ incognito, onOpenModels }) {
  let inputRef, endRef
  const quickPrompts = createMemo(() => { lang(); return pickSuggestions() })
  const [cancelFn, setCancelFn] = createSignal(null)
  const [showCfg, setShowCfg]         = createSignal(false)
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
  async function onPickFiles(fileList) {
    const picked = Array.from(fileList || [])
    const out = []
    for (const f of picked) {
      if (f.size > 512 * 1024) { out.push({ name: f.webkitRelativePath || f.name, text: `[archivo omitido: ${(f.size/1024/1024).toFixed(1)} MB, demasiado grande]` }); continue }
      try {
        const text = await f.text()
        out.push({ name: f.webkitRelativePath || f.name, text: text.slice(0, 20000) })
      } catch {
        out.push({ name: f.webkitRelativePath || f.name, text: '[no se pudo leer como texto]' })
      }
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

  createEffect(() => {
    chatState.messages.length
    streamContent()
    setTimeout(() => endRef?.scrollIntoView({ behavior:'smooth', block:'end' }), 50)
  })

  function send(promptOverride) {
    const prompt = (typeof promptOverride === 'string' ? promptOverride : inputRef?.value || '').trim()
    if (!prompt || chatState.isStreaming) return
    if (inputRef) { inputRef.value = ''; inputRef.style.height = 'auto' }

    // Adjuntar contenido de archivos como contexto antes del prompt del usuario
    const att = files()
    let fullPrompt = prompt
    if (att.length) {
      const blocks = att.map(f => `--- Archivo: ${f.name} ---\n${f.text}`).join('\n\n')
      fullPrompt = `Tengo estos archivos adjuntos como contexto:\n\n${blocks}\n\n---\n\n${prompt}`
    }

    addUserMessage(prompt)
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
      conversation_history: chatState.messages
        .filter(m => !m.streaming && m.content && m.role)
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
        } catch {}
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

  function onInput(e) {
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
  }
  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const sysOk   = () => health()?.status !== 'down'
  const specOk  = () => health()?.specialists?.active > 0
  const canSend = () => sysOk() && specOk() && !chatState.isStreaming

  const placeholder = () => {
    if (!sysOk())      return 'Sistema no disponible — verifica Ollama'
    if (!specOk())     return 'Sin IAs activas — ve a Modelos de IA'
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
              <img src="/andromeda-logo.png" alt="" style="width:72px;height:72px;object-fit:contain;margin-bottom:20px;animation:pulse 3s ease-in-out infinite" />
              <div style="font-size:24px;font-weight:800;letter-spacing:-0.02em;margin-bottom:10px">
                {incognito?.() ? t('incognito.title') : 'Andromeda'}
              </div>
              <div style="font-size:14px;color:var(--text-3);max-width:440px;line-height:1.6;margin-bottom:28px">
                <Show when={!sysOk()}>
                  <span style="color:var(--red)">{t("chat.sys_down")}</span>
                </Show>
                <Show when={sysOk() && !specOk()}>
                  <Show when={ollamaModels().length === 0} fallback={
                    <>{t("chat.no_ai_pre")}<span style="color:var(--teal)">{t("chat.ai_models")}</span>{t("chat.no_ai_post")}</>
                  }>
                    Aún no tienes ningún modelo instalado. Andromeda funciona con tus propios modelos locales — elige uno para empezar.
                  </Show>
                </Show>
                <Show when={sysOk() && specOk()}>
                  <Show when={isPro()} fallback={t('incognito.subtitle')}>
                    El orquestador seleccionará automáticamente los mejores especialistas para cada pregunta.
                  </Show>
                </Show>
              </div>

              {/* Onboarding: no hay IA activa → guía de primeros pasos.
                  Se muestra tanto si no hay modelos instalados como si hay
                  pero ninguno está activado todavía. */}
              <Show when={sysOk() && !specOk()}>
                <div style="max-width:520px;width:100%;text-align:left;background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:16px;padding:22px 24px">
                  <div style="font-size:14px;font-weight:700;margin-bottom:14px;text-align:center">{t('ui2.first_steps')}</div>
                  <div style="display:flex;flex-direction:column;gap:14px">
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0">1</div>
                      <div style="font-size:13px;color:var(--text-2);line-height:1.55">
                        Abre <span style="color:var(--teal);font-weight:600">{t('ui2.ai_models')}</span> en el menú lateral.
                      </div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0">2</div>
                      <div style="font-size:13px;color:var(--text-2);line-height:1.55">
                        <Show when={ollamaModels().length === 0} fallback={
                          <>{t("chat.tab_pre")}<span style="color:var(--text-1);font-weight:600">{t("chat.specialists")}</span>{t("chat.tab_post")}</>
                        }>
                          Descarga un modelo (en <span style="color:var(--text-1);font-weight:600">{t('ui2.explore_models')}</span>). Si es tu primera vez, <span style="color:var(--text-1);font-weight:600">llama3.2:3b</span> o <span style="color:var(--text-1);font-weight:600">qwen2.5:7b</span> son buenos para empezar.
                        </Show>
                      </div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:flex-start">
                      <div style="width:24px;height:24px;border-radius:50%;background:var(--grad-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0">3</div>
                      <div style="font-size:13px;color:var(--text-2);line-height:1.55">
                        Vuelve aquí y ya puedes chatear, crear archivos y ejecutar código — todo en local.
                      </div>
                    </div>
                  </div>
                  <button onClick={() => onOpenModels?.()}
                    class="btn btn-primary" style="width:100%;margin-top:18px"
                    >{t('ui2.go_models')}</button>
                </div>
              </Show>
              <Show when={sysOk() && specOk()}>
                <div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;max-width:560px">
                  <For each={quickPrompts()}>
                    {(p) => (
                      <button
                        onClick={() => send(p)}
                        class="glass"
                        style="padding:10px 16px;border-radius:var(--r-sm);font-size:13px;color:var(--text-2);cursor:pointer;transition:all 0.2s;background:var(--glass);font-family:var(--font)"
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
                  <span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:8px;padding:4px 8px;color:var(--text-2);max-width:220px">
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
                <div style="font-size:16px;font-weight:700;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center">
                  Añadir imágenes
                  <button onClick={() => setShowImages(false)} style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:18px">✕</button>
                </div>
                <ImageUpload onImages={setImages} />
              </div>
            </div>
          </Show>

          {/* INPUT BAR EXPANDIBLE — se agranda cuando showCfg está activo */}
          <div class="liquid-glass" style={`border-radius:26px;padding:12px;transition:all 0.3s cubic-bezier(0.4,0,0.2,1);${showCfg()?'display:flex;flex-direction:column;gap:10px':'padding:8px 8px 8px 10px'}`}>
            {/* Panel de configuración — se muestra dentro cuando showCfg es true */}
            <Show when={showCfg()}>
              <div class="ias-expand" style="display:flex;flex-direction:column;gap:10px;padding:4px 4px 12px;border-bottom:1px solid var(--glass-border);max-height:54vh;overflow-y:auto">
                <div style="font-size:14px;font-weight:700;letter-spacing:-0.01em;display:flex;justify-content:space-between;align-items:center;color:var(--text-1)">
                  {isPro() ? t('chat.cfg_title_pro') : t('chat.power_title')}
                  <button onClick={() => setShowCfg(false)} title={t("chat.close")} style="display:flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:var(--hover-surface);border:1px solid var(--glass-border);color:var(--text-3);cursor:pointer;transition:all .15s">
                    <svg width="13" height="13" viewBox="0 0 16 16"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                  </button>
                </div>
                <Show when={forceModel()}>
                  <div style="font-size:12px;padding:10px 12px;border-radius:12px;background:var(--inset-surface);border:1px solid var(--glass-border);color:var(--text-2);display:flex;justify-content:space-between;align-items:center;gap:10px">
                    <span>{t("chat.forcing_pre")}<b style="color:var(--text-1)">{forceModel()}</b>{t("chat.forcing_post")}</span>
                    <button onClick={() => setForceModel('')} style="background:var(--grad-primary);border:none;color:#fff;cursor:pointer;font-size:11px;font-weight:600;padding:5px 12px;border-radius:8px;white-space:nowrap">{t('ui2.back_auto')}</button>
                  </div>
                </Show>
                <ChatSettings onChange={setChatCfg} forceModel={forceModel()} setForceModel={setForceModel} ollamaModels={ollamaModels()} onApplied={() => { setShowCfg(false) }} />
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
                style="flex:1;background:transparent;border:none;outline:none;resize:none;color:var(--text-1);font-family:var(--font);font-size:15px;padding:10px 8px;max-height:160px;line-height:1.5"
              />
              <button
                onClick={chatState.isStreaming ? cancel : () => send()}
                disabled={!canSend() && !chatState.isStreaming}
                style={`width:42px;height:42px;border-radius:20px;border:none;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s;background:${(canSend()||chatState.isStreaming)?'var(--grad-primary)':'rgba(255,255,255,0.08)'};color:${(canSend()||chatState.isStreaming)?'white':'var(--text-3)'};${(canSend()||chatState.isStreaming)?'box-shadow:0 4px 14px rgba(240,164,140,0.35)':''}`}
                title={chatState.isStreaming ? 'Cancelar' : 'Enviar (Enter)'}
              >
                <Show when={chatState.isStreaming} fallback="↑">✕</Show>
              </button>
            </div>
          </div>

          {/* Footer con botones de acción */}
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding:0 6px;gap:10px;flex-wrap:wrap">
            <span style="font-size:11px;color:var(--text-3)">{t("chat.send_hint")}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <ChatActionBtn title={t("chat.prompts")} active={showLibrary()} onClick={() => { setShowLibrary(v=>!v); setShowCfg(false); setShowImages(false) }}><IconBook /></ChatActionBtn>
              <ChatActionBtn label={images().length ? String(images().length) : ''} title={t("chat.add_images")} active={showImages()} onClick={() => { setShowImages(v=>!v); setShowCfg(false); setShowLibrary(false) }}><IconImage /></ChatActionBtn>
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
              <ChatActionBtn label={isPro() ? 'IAs' : t('chat.power_btn')} title={isPro() ? t('chat.cfg_btn_title_pro') : t('chat.power_btn_title')} active={showCfg()} onClick={() => { setShowCfg(v=>!v); setShowImages(false); setShowLibrary(false) }}><IconSliders /></ChatActionBtn>
              <Show when={chatState.messages.length > 0 && !chatState.isStreaming}>
                <ExportButton />
              </Show>
              <Show when={specOk() && isPro()}>
                <span style="font-size:11px;color:var(--text-3);display:flex;align-items:center;gap:5px;margin-left:4px">
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
      style={`display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;padding:6px 11px;border-radius:10px;cursor:pointer;font-family:var(--font);transition:all 0.15s;border:1px solid ${props.active?'var(--glass-border)':'transparent'};background:${props.active?'var(--glass-bright)':'var(--hover-surface)'};color:${props.active?'var(--text-1)':'var(--text-3)'}`}
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
