/**
 * ExportButton.jsx — Exportar conversación en múltiples formatos.
 * Formatos: Markdown, JSON, texto plano.
 */
import { createSignal, Show } from 'solid-js'
import { chatState } from '../stores/chat.js'
import { t } from '../stores/i18n.js'
import { saveTextFile } from '../services/download.js'

function toMarkdown(messages) {
  const lines = ['# Conversación Andromeda', `*Exportado: ${new Date().toLocaleString('es-ES')}*`, '']
  for (const m of messages) {
    if (m.streaming) continue
    const role = m.role === 'user' ? '**Usuario**' : '**Andromeda**'
    const time = new Date(m.timestamp).toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'})
    lines.push(`### ${role} — ${time}`)
    lines.push(m.content || '')
    if (m.metadata?.strategy_used) lines.push(`*Estrategia: ${m.metadata.strategy_used} · ${Math.round(m.metadata.latency_ms || 0)}ms*`)
    lines.push('')
  }
  return lines.join('\n')
}

function toPlainText(messages) {
  return messages
    .filter(m => !m.streaming)
    .map(m => `[${m.role === 'user' ? 'Usuario' : 'Andromeda'}] ${m.content}`)
    .join('\n\n')
}

// La descarga por blob deja la ventana de escritorio navegando al contenido
// (pantalla de texto plano sin vuelta atrás). saveTextFile lo escribe en disco.

export default function ExportButton() {
  const [open, setOpen] = createSignal(false)
  const messages = () => chatState.messages.filter(m => !m.streaming && m.content)
  const disabled = () => messages().length === 0

  const ts = () => new Date().toISOString().slice(0,10)

  const [note, setNote] = createSignal('')

  async function exportAs(format) {
    const msgs = messages()
    let content, filename, mime
    if (format === 'md') {
      content = toMarkdown(msgs); filename = `andromeda-chat-${ts()}.md`; mime = 'text/markdown'
    } else if (format === 'json') {
      content = JSON.stringify({ exported: new Date().toISOString(), messages: msgs }, null, 2)
      filename = `andromeda-chat-${ts()}.json`; mime = 'application/json'
    } else {
      content = toPlainText(msgs); filename = `andromeda-chat-${ts()}.txt`; mime = 'text/plain'
    }
    setOpen(false)
    const r = await saveTextFile(filename, content, mime)
    setNote(r.ok ? t('mb.saved_to_downloads') : t('mb.save_error'))
    setTimeout(() => setNote(''), 3000)
  }

  return (
    <div style="position:relative">
      <Show when={note()}>
        <div style="position:absolute;top:100%;right:0;margin-top:6px;white-space:nowrap;font-size:var(--fs-xs);color:var(--text-3);background:var(--glass-bright);border:1px solid var(--glass-border);border-radius:8px;padding:5px 10px;z-index:50">
          {note()}
        </div>
      </Show>
      <button
        onClick={() => setOpen(v => !v)}
        disabled={disabled()}
        title={t('exp.export_conv')}
        style={`display:flex;align-items:center;gap:6px;font-size:var(--fs-xs);font-weight:600;padding:6px 11px;border-radius:10px;cursor:pointer;font-family:var(--font);transition:all 0.15s;border:1px solid ${open()?'var(--glass-border)':'transparent'};background:${open()?'var(--glass-bright)':'var(--hover-surface)'};color:${open()?'var(--text-1)':'var(--text-3)'}`}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        {t('exp.export')}
      </button>
      <Show when={open()}>
        {/* Click outside to close */}
        <div style="position:fixed;inset:0;z-index:99" onClick={() => setOpen(false)} />
        <div style={`
          position:absolute;bottom:calc(100% + 6px);right:0;
          background:var(--glass-bright,rgba(8,10,20,.97));border:1px solid var(--glass-border);
          border-radius:14px;padding:6px;min-width:150px;
          box-shadow:var(--shadow,0 8px 30px rgba(0,0,0,.4));z-index:100;
          backdrop-filter:blur(20px);animation:toastIn .15s ease;
        `}>
          {[
            { fmt:'md',   icon:'#', label:'Markdown (.md)' },
            { fmt:'json', icon:'{}', label:'JSON (.json)' },
            { fmt:'txt',  icon:'T', label:'Texto (.txt)' },
          ].map(({ fmt, icon, label }) => (
            <button
              onClick={() => exportAs(fmt)}
              style="width:100%;text-align:left;padding:8px 10px;background:none;border:none;color:var(--text-2);cursor:pointer;font-family:var(--font);font-size:var(--fs-sm);border-radius:10px;display:flex;align-items:center;gap:9px;transition:background .1s"
              onMouseEnter={e => e.currentTarget.style.background = 'var(--hover-surface)'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              <span style="font-family:var(--mono);font-size:var(--fs-micro);color:var(--text-3);min-width:18px">{icon}</span>
              {label}
            </button>
          ))}
        </div>
      </Show>
    </div>
  )
}
