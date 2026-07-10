/**
 * CodeSandbox.jsx — Ejecuta código directamente desde el chat.
 * Botón "▶ Ejecutar" aparece bajo los bloques de código.
 * Muestra stdout/stderr y tiempo de ejecución.
 */
import { createSignal, Show } from 'solid-js'
import axios from 'axios'

export default function CodeSandbox({ code, language = 'python' }) {
  const [running, setRunning]   = createSignal(false)
  const [result, setResult]     = createSignal(null)
  const [show, setShow]         = createSignal(false)

  const LANG_ICONS = { python: '🐍', javascript: '⚡', bash: '💻', powershell: '🪟' }

  async function run() {
    setRunning(true)
    setShow(true)
    try {
      const r = await axios.post('/api/sandbox/run', {
        code, language,
        timeout: 30,
      })
      setResult(r.data)
    } catch (e) {
      setResult({ success: false, stderr: e.message, stdout: '', elapsed_ms: 0 })
    }
    setRunning(false)
  }

  return (
    <div style="margin-top:4px">
      <button
        onClick={run}
        disabled={running()}
        style={`
          font-size:10px;padding:3px 10px;border-radius:6px;
          background:${running() ? 'var(--surface)' : 'rgba(0,212,170,.12)'};
          border:1px solid ${running() ? 'var(--border)' : 'rgba(0,212,170,.3)'};
          color:${running() ? 'var(--text-3)' : 'var(--teal)'};
          cursor:${running() ? 'not-allowed' : 'pointer'};
          display:flex;align-items:center;gap:5px;
          transition:all .12s;font-family:var(--font);
        `}
      >
        <Show when={running()} fallback={<>▶ Ejecutar {LANG_ICONS[language] || ''}</>}>
          <span class="spin" style="width:8px;height:8px;border-width:1.5px" /> corriendo...
        </Show>
      </button>

      <Show when={show() && result()}>
        <div class="sandbox-result">
          <div class="sandbox-header">
            <span class={result()?.success ? 'sandbox-ok' : 'sandbox-err'}>
              {result()?.success ? '✓ OK' : '✗ Error'}
            </span>
            <span style="color:var(--text-3)">{language}</span>
            <Show when={result()?.timed_out}>
              <span style="color:var(--amber)">⏱ timeout</span>
            </Show>
            <span class="sandbox-time">{result()?.elapsed_ms}ms</span>
          </div>
          <Show when={result()?.stdout}>
            <div class="sandbox-body">{result().stdout}</div>
          </Show>
          <Show when={result()?.stderr}>
            <div class="sandbox-body sandbox-err" style="border-top:1px solid var(--border)">
              {result().stderr}
            </div>
          </Show>
          <Show when={!result()?.stdout && !result()?.stderr}>
            <div class="sandbox-body" style="color:var(--text-3)">(sin output)</div>
          </Show>
        </div>
      </Show>
    </div>
  )
}
