/**
 * Codex.jsx — Editor de código tipo IDE integrado en Andromeda.
 * Escribe código, elige lenguaje, ejecútalo y ve la salida en vivo.
 * Usa el endpoint /api/sandbox/run (sandbox seguro del backend).
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import bash from 'highlight.js/lib/languages/bash'
import powershell from 'highlight.js/lib/languages/powershell'
import ruby from 'highlight.js/lib/languages/ruby'
import php from 'highlight.js/lib/languages/php'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import lua from 'highlight.js/lib/languages/lua'
import perl from 'highlight.js/lib/languages/perl'
import r from 'highlight.js/lib/languages/r'
import 'highlight.js/styles/atom-one-dark.css'
import { t } from '../stores/i18n.js'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('powershell', powershell)
hljs.registerLanguage('ruby', ruby)
hljs.registerLanguage('php', php)
hljs.registerLanguage('go', go)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('lua', lua)
hljs.registerLanguage('perl', perl)
hljs.registerLanguage('r', r)

const SNIPPETS = {
  python: '# Python\nfor i in range(5):\n    print(f"Línea {i}")\n',
  javascript: '// JavaScript\nfor (let i = 0; i < 5; i++) {\n  console.log(`Línea ${i}`)\n}\n',
  typescript: '// TypeScript\nconst nums: number[] = [1,2,3,4,5]\nnums.forEach(n => console.log(`Línea ${n}`))\n',
  bash: '# Bash\nfor i in 1 2 3 4 5; do\n  echo "Línea $i"\ndone\n',
  powershell: '# PowerShell\n1..5 | ForEach-Object { Write-Output "Línea $_" }\n',
  ruby: '# Ruby\n(1..5).each { |i| puts "Línea #{i}" }\n',
  php: '<?php\nfor ($i = 1; $i <= 5; $i++) {\n  echo "Línea $i\\n";\n}\n',
  go: '// Go\npackage main\nimport "fmt"\nfunc main() {\n  for i := 1; i <= 5; i++ {\n    fmt.Printf("Línea %d\\n", i)\n  }\n}\n',
  rust: '// Rust\nfn main() {\n  for i in 1..=5 {\n    println!("Línea {}", i);\n  }\n}\n',
  lua: '-- Lua\nfor i = 1, 5 do\n  print("Línea " .. i)\nend\n',
  perl: '# Perl\nforeach my $i (1..5) {\n  print "Línea $i\\n";\n}\n',
  r: '# R\nfor (i in 1:5) {\n  cat("Línea", i, "\\n")\n}\n',
}

const LANG_LABEL = {
  python: 'Python', javascript: 'JavaScript', typescript: 'TypeScript', bash: 'Bash',
  powershell: 'PowerShell', ruby: 'Ruby', php: 'PHP', go: 'Go', rust: 'Rust',
  lua: 'Lua', perl: 'Perl', r: 'R',
}


export default function Codex() {
  const ALL_LANGS = Object.keys(LANG_LABEL)   // todos los soportados (orden fijo)
  const [avail, setAvail]     = createSignal({})   // { python: true, go: false, ... }
  const [lang, setLang]       = createSignal('python')
  const [code, setCode]       = createSignal(SNIPPETS.python)
  const [running, setRunning] = createSignal(false)
  const [result, setResult]   = createSignal(null)
  const [history, setHistory] = createSignal([])   // ejecuciones previas
  const [installing, setInstalling] = createSignal(null)  // id del lenguaje instalándose
  const [installMsg, setInstallMsg] = createSignal('')

  // Lista a renderizar: SIEMPRE todos los lenguajes; available marca si hay intérprete
  const langs = () => ALL_LANGS.map(id => ({ id, available: avail()[id] !== false }))

  onMount(async () => {
    try {
      const r = await axios.get('/api/sandbox/languages')
      const map = {}
      for (const l of (r.data.languages || [])) map[l.id] = l.available !== false
      setAvail(map)
    } catch (e) {
      setAvail({ python: true, javascript: true, bash: true })
    }
  })

  function changeLang(l) {
    setLang(l)
    // Solo cambia el snippet si el editor está en un snippet por defecto (no pisar trabajo del usuario)
    if (Object.values(SNIPPETS).includes(code())) setCode(SNIPPETS[l] || '')
  }

  async function refreshLangs() {
    try {
      const r = await axios.get('/api/sandbox/languages')
      const map = {}
      for (const l of (r.data.languages || [])) map[l.id] = l.available !== false
      setAvail(map)
    } catch { /* noop */ }
  }

  async function installLang(id) {
    setInstalling(id)
    setInstallMsg('')
    try {
      const r = await axios.post('/api/sandbox/install', { language: id })
      const d = r.data
      if (d.success && d.available_now) {
        setInstallMsg(t('codex.install_ok'))
        await refreshLangs()
      } else if (d.needs_restart) {
        setInstallMsg(t('codex.install_restart'))
      } else if (d.manual && d.url) {
        setInstallMsg(t('codex.install_manual'))
        window.open(d.url, '_blank')
      } else {
        setInstallMsg(d.message || t('codex.install_fail'))
        if (d.url) window.open(d.url, '_blank')
      }
    } catch {
      setInstallMsg(t('codex.install_fail'))
    }
    setInstalling(null)
  }

  async function run() {
    setRunning(true)
    setResult(null)
    const started = Date.now()
    try {
      const r = await axios.post('/api/sandbox/run', { code: code(), language: lang(), timeout: 30 })
      setResult(r.data)
      setHistory(h => [{ lang: lang(), success: r.data.success, ts: Date.now() }, ...h].slice(0, 5))
    } catch (e) {
      setResult({ success: false, stderr: e.response?.data?.error || e.message, stdout: '', elapsed_ms: Date.now() - started })
    }
    setRunning(false)
  }

  // Tab inserta 4 espacios en vez de cambiar de foco
  function onKeyDown(e) {
    if (e.key === 'Tab') {
      e.preventDefault()
      const ta = e.target
      const start = ta.selectionStart, end = ta.selectionEnd
      const v = code()
      setCode(v.slice(0, start) + '    ' + v.slice(end))
      requestAnimationFrame(() => { ta.selectionStart = ta.selectionEnd = start + 4 })
    }
    // Ctrl/Cmd + Enter ejecuta
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run() }
  }

  const lineCount = () => code().split('\n').length

  // Código resaltado para la capa de debajo (highlight.js)
  const highlighted = () => {
    try {
      const lng = hljs.getLanguage(lang()) ? lang() : 'plaintext'
      const html = hljs.highlight(code(), { language: lng }).value
      return html + '\n'
    } catch {
      return code() + '\n'
    }
  }

  // Sincronizar scroll entre textarea (encima) y pre resaltado (debajo)
  let preRef, taRef
  function syncScroll() {
    if (preRef && taRef) {
      preRef.scrollTop = taRef.scrollTop
      preRef.scrollLeft = taRef.scrollLeft
    }
  }

  return (
    <div style="padding:24px;max-width:1000px;margin:0 auto">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <div>
          <div style="font-size:22px;font-weight:800;letter-spacing:-0.02em">Codex</div>
          <div style="font-size:13px;color:var(--text-3)">{t('codex.subtitle')}</div>
        </div>
      </div>

      {/* Barra de lenguajes — todos seleccionables; el punto indica si hay intérprete */}
      <div style="display:flex;gap:8px;margin:18px 0;flex-wrap:wrap">
        <For each={langs()}>
          {(l) => (
            <button
              onClick={() => changeLang(l.id)}
              class="btn"
              title={l.available ? `${LANG_LABEL[l.id]} — listo para ejecutar` : `${LANG_LABEL[l.id]} — editable; instala el intérprete para ejecutar`}
              style={`font-size:13px;padding:8px 14px;display:flex;align-items:center;gap:7px;${lang()===l.id
                ? 'background:var(--grad-primary);color:#fff'
                : 'background:var(--glass-bright);color:var(--text-2);border:1px solid var(--glass-border)'}`}>
              <span style={`width:6px;height:6px;border-radius:50%;flex-shrink:0;background:${l.available ? 'var(--green)' : 'var(--text-3)'}`} />
              {LANG_LABEL[l.id] || l.id}
            </button>
          )}
        </For>
      </div>

      <Show when={avail()[lang()] === false}>
        <div style="font-size:12px;color:var(--text-2);background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:10px;padding:9px 12px;margin:-6px 0 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span style="flex:1;min-width:200px">
            Puedes escribir y guardar {LANG_LABEL[lang()]}, pero para <b>ejecutarlo</b> necesitas su intérprete.
            <Show when={installMsg()}><span style="color:var(--text-3);display:block;margin-top:4px">{installMsg()}</span></Show>
          </span>
          <button class="btn btn-primary" style="font-size:12px;padding:6px 12px;white-space:nowrap"
            disabled={installing() === lang()}
            onClick={() => installLang(lang())}>
            {installing() === lang() ? t('codex.installing') : t('codex.install_btn')}
          </button>
        </div>
      </Show>

      {/* Editor */}
      <div class="card" style="padding:0;overflow:hidden;border-radius:14px">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--glass-border);background:rgba(0,0,0,0.2)">
          <div style="display:flex;gap:7px;align-items:center">
            <span style="width:11px;height:11px;border-radius:50%;background:#ff5f57"></span>
            <span style="width:11px;height:11px;border-radius:50%;background:#febc2e"></span>
            <span style="width:11px;height:11px;border-radius:50%;background:#28c840"></span>
            <span style="font-size:12px;color:var(--text-3);margin-left:10px;font-family:var(--font-mono)">script{lang()==='python'?'.py':lang()==='javascript'?'.js':'.sh'}</span>
          </div>
          <span style="font-size:11px;color:var(--text-3)">{lineCount()} líneas</span>
        </div>
        <div class="codex-editor" style="position:relative;min-height:300px">
          {/* Capa de resaltado (debajo) */}
          <pre ref={preRef} aria-hidden="true"
            style="margin:0;padding:16px;font-family:var(--font-mono);font-size:13px;line-height:1.6;tab-size:4;white-space:pre;overflow:auto;position:absolute;inset:0;pointer-events:none;color:var(--text-1)"
          ><code class={`language-${lang()} hljs`} innerHTML={highlighted()} /></pre>
          {/* Textarea transparente (encima) */}
          <textarea
            ref={taRef}
            value={code()}
            onInput={e => setCode(e.target.value)}
            onKeyDown={onKeyDown}
            onScroll={syncScroll}
            spellcheck={false}
            style="width:100%;min-height:300px;background:transparent;border:none;outline:none;resize:none;padding:16px;font-family:var(--font-mono);font-size:13px;line-height:1.6;letter-spacing:0;color:transparent;caret-color:var(--text-1);tab-size:4;white-space:pre;overflow:auto;position:relative;z-index:1"
          />
        </div>
      </div>

      {/* Acciones */}
      <div style="display:flex;gap:10px;margin-top:14px;align-items:center">
        <button class="btn btn-primary" onClick={run} disabled={running()} style="font-size:14px;padding:10px 22px">
          <Show when={!running()} fallback={<><span class="spin" /> Ejecutando...</>}>{t('cdx.run')}</Show>
        </button>
        <span style="font-size:12px;color:var(--text-3)">o pulsa <kbd style="background:rgba(255,255,255,0.08);padding:2px 7px;border-radius:5px;font-family:var(--font-mono)">Ctrl/Cmd + Enter</kbd></span>
      </div>

      {/* Resultado */}
      <Show when={result()}>
        <div class="card anim-spring" style="margin-top:18px;padding:0;overflow:hidden;border-radius:14px">
          <div style={`display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--glass-border);background:${result().success?'rgba(40,200,100,0.08)':'rgba(255,95,87,0.08)'}`}>
            <span style={`font-size:13px;font-weight:700;color:${result().success?'var(--green)':'var(--red)'}`}>
              {result().success ? t('js.exec_ok') : t('js.exec_err')}
            </span>
            <span style="font-size:11px;color:var(--text-3)">{result().elapsed_ms} ms</span>
          </div>
          <div style="padding:16px">
            <Show when={result().stdout}>
              <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;font-weight:700;margin-bottom:6px">Salida</div>
              <pre style="margin:0 0 14px;font-family:var(--font-mono);font-size:13px;color:var(--text-1);white-space:pre-wrap;word-break:break-word">{result().stdout}</pre>
            </Show>
            <Show when={result().stderr}>
              <div style="font-size:10px;color:var(--red);text-transform:uppercase;font-weight:700;margin-bottom:6px">{t('common.errors')}</div>
              <pre style="margin:0;font-family:var(--font-mono);font-size:13px;color:#ff9b94;white-space:pre-wrap;word-break:break-word">{result().stderr}</pre>
            </Show>
            <Show when={!result().stdout && !result().stderr}>
              <div style="font-size:13px;color:var(--text-3);font-style:italic">{t('ui2.no_output')}</div>
            </Show>
          </div>
        </div>
      </Show>

      {/* Aviso de seguridad */}
      <div style="margin-top:18px;padding:12px 14px;background:rgba(123,140,240,0.08);border-left:3px solid var(--blue);border-radius:8px;font-size:12px;color:var(--text-2)">
        El código corre en un sandbox aislado con límite de tiempo (30s) y sin acceso a tus archivos. Ideal para probar fragmentos rápido.
      </div>
    </div>
  )
}
