/**
 * MessageBubble.jsx — Burbuja de mensaje mejorada.
 * - Copy de bloques de código con un click
 * - Specialist badge inline cuando hay metadata
 * - Indicador de error visual
 * - Latencia + especialistas en el footer del mensaje
 */
import { showLatency, showBadges } from '../stores/settings'
import { t } from '../stores/i18n.js'
import { Show, createSignal, For } from 'solid-js'
import { streamContent, streamSpecialist, streamProgress, streamPlaceholder } from '../stores/chat.js'
import CodeSandbox from './CodeSandbox.jsx'
import { marked } from 'marked'

// Configurar marked: saltos de línea como en GitHub, sin IDs en headers.
marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false })

const SPEC_COLORS = {
  'software-engineering': '#5b9cf6',
  'generalist':           '#00d4aa',
  'it-ops':               '#34d399',
  'technical-writer':     '#a78bfa',
  'verifier':             '#fbbf24',
  'summarizer':           '#f472b6',
  'orchestrator':         '#94a3b8',
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = createSignal(false)
  const execLangs = ['python', 'py', 'javascript', 'js', 'bash', 'sh']
  const canRun = () => execLangs.includes((lang || '').toLowerCase())
  const normLang = () => {
    const l = (lang || '').toLowerCase()
    if (l === 'py') return 'python'
    if (l === 'js') return 'javascript'
    if (l === 'sh') return 'bash'
    return l || 'python'
  }

  function copy() {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Extensión de archivo según el lenguaje, para descargar el bloque.
  const EXT = {
    python: 'py', py: 'py', javascript: 'js', js: 'js', typescript: 'ts',
    bash: 'sh', sh: 'sh', json: 'json', yaml: 'yml', yml: 'yml', html: 'html',
    css: 'css', sql: 'sql', java: 'java', go: 'go', rust: 'rs', c: 'c',
    cpp: 'cpp', markdown: 'md', md: 'md', dockerfile: 'Dockerfile',
  }
  function download() {
    const l = (lang || 'txt').toLowerCase()
    const ext = EXT[l] || 'txt'
    const name = ext === 'Dockerfile' ? 'Dockerfile' : `andromeda-snippet.${ext}`
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = name; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div style="position:relative;margin:10px 0">
      <div style="display:flex;align-items:center;justify-content:space-between;background:rgba(0,0,0,.4);border:1px solid var(--border);border-bottom:none;border-radius:var(--r-sm) var(--r-sm) 0 0;padding:5px 12px">
        <span style="font-size:10px;color:var(--text-3);font-family:var(--mono)">{lang || 'code'}</span>
        <div style="display:flex;align-items:center;gap:12px">
          <button
            onClick={download}
            style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;padding:2px 0;transition:color .12s"
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>descargar
          </button>
          <button
            onClick={copy}
            style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;padding:2px 0;transition:color .12s"
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            {copied() ? '✓ copiado' : '⎘ copiar'}
          </button>
        </div>
      </div>
      <pre style="background:rgba(0,0,0,.5);border:1px solid var(--border);border-radius:0 0 var(--r-sm) var(--r-sm);padding:14px;margin:0;overflow-x:auto">
        <code style="font-family:var(--mono);font-size:12.5px;color:var(--text-1);line-height:1.6">{code}</code>
      </pre>
      <Show when={canRun()}>
        <CodeSandbox code={code} language={normLang()} />
      </Show>
    </div>
  )
}

function renderContent(text) {
  if (!text) return []
  const parts = []
  const codeBlockRe = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0, m
  while ((m = codeBlockRe.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: 'text', content: text.slice(last, m.index) })
    parts.push({ type: 'code', lang: m[1], content: m[2].trim() })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ type: 'text', content: text.slice(last) })
  return parts
}

function renderText(text) {
  // Render Markdown profesional con marked (tablas, listas anidadas, links,
  // citas, etc.). Escapamos solo lo imprescindible; marked maneja el resto.
  try {
    return marked.parse(text || '')
  } catch {
    // Fallback ultra-seguro: texto plano escapado.
    return (text || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }
}

export default function MessageBubble({ message }) {
  const [copied, setCopied] = createSignal(false)
  const isUser    = message.role === 'user'
  const isError   = message.error
  const isStream  = () => message.streaming
  const content   = () => isStream() ? streamContent() : (message.content || '')
  const specialist= () => isStream() ? streamSpecialist() : null
  const meta      = message.metadata
  const [feedback, setFeedback] = createSignal(null)   // 'up' | 'down' | null

  async function sendFeedback(positive) {
    const next = positive ? 'up' : 'down'
    const newVal = feedback() === next ? null : next
    setFeedback(newVal)
    if (newVal === null) return            // se deseleccionó: no enviar
    try {
      await fetch('/api/feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: meta?.request_id || '',
          positive,
          model: meta?.models_used ? Object.values(meta.models_used)[0] : null,
          ab_experiment: meta?.ab_experiment || null,
          ab_variant: meta?.ab_variant || null,
        }),
      })
    } catch { /* feedback es best-effort */ }
  }

  function copyAll() {
    navigator.clipboard.writeText(content())
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const [docMenu, setDocMenu] = createSignal(false)
  async function exportDocument(fmt) {
    try {
      const resp = await fetch('/api/documents/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: content(),
          format: fmt,
          title: 'Andromeda ' + new Date().toLocaleDateString('es-ES'),
        }),
      })
      if (!resp.ok) throw new Error('HTTP ' + resp.status)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `andromeda-${Date.now()}.${fmt}`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      console.error('Error exportando documento:', e)
    }
  }

  const parts = () => isUser ? null : renderContent(content())

  return (
    <div class={`msg ${isUser ? 'msg-user' : 'msg-ai'}`}>
      {/* Specialist badge — solo para respuestas de IA */}
      <Show when={showBadges() && !isUser && (specialist() || meta?.specialists_used?.length > 0)}>
        <div style="display:flex;align-items:center;gap:5px;padding:0 4px;flex-wrap:wrap">
          <For each={specialist() ? [specialist()] : (meta?.specialists_used || [])}>
            {(sid) => (
              <span style={`
                font-size:10px;font-weight:600;padding:2px 7px;border-radius:8px;
                background:${SPEC_COLORS[sid] || '#555'}18;
                border:1px solid ${SPEC_COLORS[sid] || '#555'}33;
                color:${SPEC_COLORS[sid] || 'var(--text-3)'};
                font-family:var(--mono);display:inline-flex;align-items:center;gap:5px
              `}>
                {sid}
                <Show when={meta?.models_used?.[sid]}>
                  <span style={`
                    font-size:9px;font-weight:500;padding:1px 5px;border-radius:6px;
                    background:var(--accent,#6C8CFF)22;color:var(--accent,#6C8CFF);
                    font-family:var(--mono)
                  `} title={`Modelo que respondió: ${meta.models_used[sid]}`}>
                    {meta.models_used[sid]}
                  </span>
                </Show>
              </span>
            )}
          </For>
          <Show when={isStream()}>
            <span style="font-size:10px;color:var(--text-3);display:flex;align-items:center;gap:3px">
              <span class="spin" style="width:8px;height:8px;border-width:1.5px" />
              generando
            </span>
          </Show>
        </div>
      </Show>

      {/* Bubble */}
      <div class={`bubble ${isUser ? 'bubble-user' : isError ? 'bubble-error' : 'bubble-ai'}`}>
        <Show when={isUser}>
          <span style="white-space:pre-wrap">{content()}</span>
        </Show>
        <Show when={!isUser}>
          {/* Indicador multi-IA: mientras trabajan y aún no hay respuesta final */}
          <Show when={isStream() && streamProgress() && !content()}>
            <div style="display:flex;align-items:center;gap:10px;color:var(--text-3);font-size:13px;padding:2px 0">
              <span class="spin" style="width:13px;height:13px;border-width:2px" />
              <span>
                {(() => {
                  const p = streamProgress()
                  const n = p?.working?.length || 0
                  return `${n} ${n === 1 ? 'IA analizando' : 'IAs colaborando en'} tu pregunta · fusionando respuestas…`
                })()}
              </span>
            </div>
          </Show>
          {/* Lite (1 IA): frase de espera mientras el modelo carga, sin contenido aún.
              Fallback: si está en streaming sin placeholder ni contenido (p.ej. al
              volver de otra pantalla), mostramos igualmente un indicador para que
              nunca quede "colgado" sin feedback visual. */}
          <Show when={isStream() && !content() && !streamProgress()}>
            <div style="display:flex;align-items:center;gap:10px;color:var(--text-3);font-size:13px;padding:2px 0">
              <span class="spin" style="width:13px;height:13px;border-width:2px" />
              <span>{streamPlaceholder() || t('chat.thinking')}</span>
            </div>
          </Show>
          {/* Banner de error accionable (Ollama caído / sin modelo) */}
          <Show when={meta?.error_kind}>
            {(() => {
              const kind = meta.error_kind
              const isOffline = kind === 'ollama_offline'
              const title = isOffline ? t('err.ollama_title') : t('err.model_title')
              const body  = isOffline ? t('err.ollama_body')  : t('err.model_body')
              const cta   = isOffline ? t('err.ollama_cta')   : t('err.model_cta')
              const href  = isOffline ? 'https://ollama.com/download' : null
              return (
                <div style="
                  border:1px solid var(--warn,#e0a030)55;
                  background:var(--warn,#e0a030)12;
                  border-radius:12px;padding:13px 15px;margin:4px 0;
                  display:flex;flex-direction:column;gap:7px">
                  <div style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:14px;color:var(--text-1)">
                    <span style="font-size:16px">⚠️</span>{title}
                  </div>
                  <div style="font-size:13px;line-height:1.5;color:var(--text-2)">{body}</div>
                  <div style="display:flex;gap:8px;margin-top:3px">
                    <Show when={href}>
                      <a href={href} target="_blank" rel="noopener"
                         style="font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;
                                background:var(--accent,#6c8cff);color:#fff;text-decoration:none">
                        {cta}
                      </a>
                    </Show>
                    <Show when={!href}>
                      <a href="#/models"
                         style="font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;
                                background:var(--accent,#6c8cff);color:#fff;text-decoration:none">
                        {cta}
                      </a>
                    </Show>
                  </div>
                </div>
              )
            })()}
          </Show>
          <Show when={!meta?.error_kind}>
            <For each={parts()}>
              {(part) => (
                <Show
                  when={part.type === 'code'}
                  fallback={<div class="md-content" innerHTML={renderText(part.content)} />}
                >
                  <CodeBlock code={part.content} lang={part.lang} />
                </Show>
              )}
            </For>
          </Show>
          <Show when={isStream() && content()}>
            <span class="cursor" />
          </Show>
        </Show>
      </div>

      {/* Acciones de archivo realizadas (crear, editar, borrar…) — feedback claro */}
      <Show when={!isUser && meta?.file_actions?.length > 0}>
        <div style="margin:8px 4px 0;display:flex;flex-direction:column;gap:6px">
          <For each={meta.file_actions}>
            {(fa) => {
              const ICON = { write: '📄', edit: '✏️', append: '➕', delete: '🗑️',
                             mkdir: '📁', move: '↪️', copy: '📋', read: '👁️' }
              return (
                <div style={`display:flex;align-items:center;gap:9px;padding:9px 12px;border-radius:10px;
                            border:1px solid var(--glass-border);font-size:13px;
                            background:${fa.ok ? 'var(--hover-surface)' : 'rgba(224,73,75,0.08)'}`}>
                  <span style="font-size:16px">{fa.ok ? (ICON[fa.action] || '📄') : '⚠️'}</span>
                  <span style={`color:${fa.ok ? 'var(--text-2)' : 'var(--red)'};flex:1`}>{fa.detail}</span>
                  <Show when={fa.ok}>
                    <span style="font-size:11px;color:var(--green);font-weight:600">✓</span>
                  </Show>
                </div>
              )
            }}
          </For>
        </div>
      </Show>
      <Show when={!isUser && message.rawResponses}>
        <details style="margin:6px 4px 0;font-size:11px">
          <summary style="cursor:pointer;color:var(--text-3);user-select:none">
            Ver respuestas individuales de cada IA
          </summary>
          <div style="margin-top:8px;padding:10px 12px;border-radius:10px;background:var(--hover-surface);border:1px solid var(--glass-border);white-space:pre-wrap;color:var(--text-3);font-size:12px;line-height:1.5">
            {message.rawResponses}
          </div>
        </details>
      </Show>

      {/* Footer del mensaje */}
      <div class="msg-meta">
        <span class="msg-time">
          {new Date(message.timestamp || Date.now()).toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'})}
        </span>
        <Show when={showLatency() && meta?.latency_ms}>
          <span class="msg-latency">{Math.round(meta.latency_ms)}ms</span>
        </Show>
        <Show when={meta?.strategy_used && !isUser}>
          <span style="font-size:10px;color:var(--text-3);font-family:var(--mono)">{meta.strategy_used}</span>
        </Show>
        <Show when={meta?.output_ai_used && !isUser}>
          <span style="font-size:10px;color:var(--purple, #a78bfa);font-weight:600" title={t('mb.unified')}>✨ unificada</span>
        </Show>
        <Show when={meta?.power_tier && !isUser}>
          <span style="font-size:10px;color:var(--text-3);display:inline-flex;align-items:center;gap:3px" title={`${t('msg.power_tip')}: ${meta.power_tier}/4 (${meta.complexity ?? '?'})`}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>T{meta.power_tier}
          </span>
        </Show>
        <Show when={meta?.confidence != null && !isUser}>
          <span
            style={`font-size:10px;color:${meta.confidence >= 0.7 ? 'var(--green,#4ade80)' : meta.confidence >= 0.5 ? 'var(--text-3)' : 'var(--amber,#fbbf24)'}`}
            title={`Confianza estimada de la respuesta: ${Math.round(meta.confidence * 100)}%${meta.could_escalate ? ' — Andromeda podría mejorar escalando a un modelo mayor' : ''}`}
          >
            {meta.confidence >= 0.7 ? '●' : meta.confidence >= 0.5 ? '◐' : '○'} {Math.round(meta.confidence * 100)}%
          </span>
        </Show>
        <Show when={!isUser && !isStream() && content().length > 0}>
          <button
            style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:10px;padding:0 2px;transition:color .12s"
            onClick={copyAll}
            title={t('mb.copy_full')}
          >
            {copied() ? '✓' : '⎘'}
          </button>
          <button
            style={`background:none;border:none;cursor:pointer;font-size:11px;padding:0 2px;transition:color .12s;color:${feedback()==='up' ? 'var(--green)' : 'var(--text-3)'}`}
            onClick={() => sendFeedback(true)}
            title={t('mb.useful')}
          >👍</button>
          <button
            style={`background:none;border:none;cursor:pointer;font-size:11px;padding:0 2px;transition:color .12s;color:${feedback()==='down' ? 'var(--red)' : 'var(--text-3)'}`}
            onClick={() => sendFeedback(false)}
            title={t('mb.not_useful')}
          >👎</button>
          <button
            style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:10px;padding:0 2px;transition:color .12s"
            onClick={() => {
              const blob = new Blob([content()], { type: 'text/markdown;charset=utf-8' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url; a.download = `andromeda-respuesta-${Date.now()}.md`; a.click()
              setTimeout(() => URL.revokeObjectURL(url), 1000)
            }}
            title={t('mb.dl_md')}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </button>
          <span style="position:relative;display:inline-block">
            <button
              style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:10px;padding:0 2px;transition:color .12s"
              onClick={() => setDocMenu(v => !v)}
              title={t('mb.export_doc')}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>exportar
            </button>
            <Show when={docMenu()}>
              <div
                style="position:fixed;inset:0;z-index:19"
                onClick={() => setDocMenu(false)}
              />
              <div style="position:absolute;bottom:100%;left:0;margin-bottom:4px;background:var(--surface-2,#1a1a22);border:1px solid var(--glass-border);border-radius:8px;padding:4px;z-index:20;min-width:120px;box-shadow:0 4px 16px rgba(0,0,0,.4)">
                <For each={[['docx','Word (.docx)'],['pdf','PDF (.pdf)'],['xlsx','Excel (.xlsx)']]}>
                  {([fmt, label]) => (
                    <button
                      style="display:block;width:100%;text-align:left;background:none;border:none;color:var(--text-2);cursor:pointer;font-size:12px;padding:6px 10px;border-radius:5px"
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--hover-surface)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'none'}
                      onClick={() => { exportDocument(fmt); setDocMenu(false) }}
                    >{label}</button>
                  )}
                </For>
              </div>
            </Show>
          </span>
        </Show>
      </div>
    </div>
  )
}
