/**
 * ExportButton.jsx — Exportar conversación en múltiples formatos.
 * Formatos: Markdown, JSON, texto plano.
 */
import { createSignal, Show } from 'solid-js'
import { chatState } from '../stores/chat.js'
import { t } from '../stores/i18n.js'

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

function download(content, filename, type) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function ExportButton() {
  const [open, setOpen] = createSignal(false)
  const messages = () => chatState.messages.filter(m => !m.streaming && m.content)
  const disabled = () => messages().length === 0

  const ts = () => new Date().toISOString().slice(0,10)

  function exportAs(format) {
    const msgs = messages()
    if (format === 'md') {
      download(toMarkdown(msgs), `andromeda-chat-${ts()}.md`, 'text/markdown')
    } else if (format === 'json') {
      download(JSON.stringify({ exported: new Date().toISOString(), messages: msgs }, null, 2),
               `andromeda-chat-${ts()}.json`, 'application/json')
    } else if (format === 'txt') {
      download(toPlainText(msgs), `andromeda-chat-${ts()}.txt`, 'text/plain')
    }
    setOpen(false)
  }

  return (
    <div style="position:relative">
      <button
        onClick={() => setOpen(v => !v)}
        disabled={disabled()}
        title={t('exp.export_conv')}
        style={`display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;padding:6px 11px;border-radius:10px;cursor:pointer;font-family:var(--font);transition:all 0.15s;border:1px solid ${open()?'var(--glass-border)':'transparent'};background:${open()?'var(--glass-bright)':'var(--hover-surface)'};color:${open()?'var(--text-1)':'var(--text-3)'}`}
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
          border-radius:12px;padding:6px;min-width:150px;
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
              style="width:100%;text-align:left;padding:8px 10px;background:none;border:none;color:var(--text-2);cursor:pointer;font-family:var(--font);font-size:12px;border-radius:8px;display:flex;align-items:center;gap:9px;transition:background .1s"
              onMouseEnter={e => e.currentTarget.style.background = 'var(--hover-surface)'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              <span style="font-family:var(--mono);font-size:10px;color:var(--text-3);min-width:18px">{icon}</span>
              {label}
            </button>
          ))}
        </div>
      </Show>
    </div>
  )
}
