/**
 * Onboarding.jsx — Pantalla de primer arranque.
 * Se muestra cuando no hay especialistas configurados.
 * Guía al usuario para instalar Ollama y descargar los modelos.
 */
import { createSignal, createEffect, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

const STARTER_MODELS = [
  { model: 'phi3.5:3.8b',      role: 'Orquestador, Verifier, Summarizer', size: '2.2GB', priority: 1 },
  { model: 'mistral:7b',       role: 'Generalist',                         size: '4.1GB', priority: 2 },
  { model: 'qwen2.5-coder:7b', role: 'Software Engineering',               size: '4.7GB', priority: 3 },
]

export default function Onboarding({ onDone }) {
  const [step, setStep]         = createSignal('check')   // check | install | models | done
  const [setup, setSetup]       = createSignal(null)
  const [checking, setChecking] = createSignal(false)
  const [copied, setCopied]     = createSignal('')
  const [checkError, setCheckError] = createSignal(false)
  const [diagInfo, setDiagInfo]     = createSignal('')   // detalle real del fallo
  const [pullProgress, setPullProgress] = createSignal({})   // { [model]: {pct,total_mb,done_mb} }

  // Lanza la descarga de un modelo y hace polling del progreso hasta acabar.
  async function downloadModel(model) {
    try {
      setPullProgress(p => ({ ...p, [model]: { pct: 0, total_mb: 0, done_mb: 0 } }))
      await axios.post('/api/models/pull', { model_name: model })
      const poll = setInterval(async () => {
        try {
          const r = await axios.get(`/api/models/pull-progress/${encodeURIComponent(model)}`)
          setPullProgress(p => ({ ...p, [model]: r.data }))
          if (r.data.pct === 100 || r.data.pct === -1) clearInterval(poll)
        } catch { clearInterval(poll) }
      }, 1200)
    } catch {
      setPullProgress(p => ({ ...p, [model]: { pct: -1, total_mb: 0, done_mb: 0 } }))
    }
  }

  async function checkSetup() {
    setChecking(true)
    try {
      const r = await axios.get('/api/health/setup', { timeout: 8000 })
      setSetup(r.data)
      if (r.data.is_ready) { onDone?.(); return }
      if (!r.data.ollama_reachable) setStep('install')
      else if (!r.data.all_models_ready) setStep('models')
      else setStep('activate')
    } catch {
      // Si el backend tarda o falla, no quedarse bloqueado en el spinner —
      // asumir que Ollama no se detectó y mostrar el paso de instalación.
      setStep('install')
    } finally {
      setChecking(false)
    }
  }

  // Auto-check on mount
  createEffect(() => { checkSetup() })

  // Versión para el botón manual: muestra error + diagnóstico si Ollama sigue
  // sin detectarse, para que el usuario vea QUÉ falla exactamente.
  async function checkSetupWithError() {
    setCheckError(false)
    setDiagInfo('')
    await checkSetup()
    if (step() === 'install') {
      setCheckError(true)
      try {
        const d = await axios.get('/api/health/diagnose', { timeout: 12000 })
        const ollama = (d.data?.checks || []).find(c => c.check?.includes('Ollama conectado'))
        if (ollama && ollama.detail) setDiagInfo(ollama.detail)
      } catch (e) {
        setDiagInfo('El backend de Andromeda no respondió. Reinicia la aplicación.')
      }
    }
  }

  function copy(text, key) {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(''), 2000)
  }

  const CMD = (text, key) => (
    <div style="display:flex;align-items:center;gap:10px;background:rgba(0,0,0,.5);border:1px solid rgba(91,156,246,.2);border-radius:8px;padding:10px 14px;margin:8px 0">
      <code style="flex:1;font-family:var(--mono);font-size:12px;color:#e8eaf0">{text}</code>
      <button
        onClick={() => copy(text, key)}
        style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;padding:2px 8px;border-radius:4px;white-space:nowrap;transition:all .12s"
        onMouseEnter={e => e.currentTarget.style.background='rgba(255,255,255,.08)'}
        onMouseLeave={e => e.currentTarget.style.background='none'}
      >
        {copied() === key ? '✓ copiado' : '⎘ copiar'}
      </button>
    </div>
  )

  return (
    <div style="height:100%;display:flex;align-items:center;justify-content:center;background:var(--bg);padding:40px">
      <div style="max-width:560px;width:100%">

        {/* Header */}
        <div style="text-align:center;margin-bottom:40px">
          <div style="font-size:13px;font-weight:700;letter-spacing:.25em;color:var(--blue);text-transform:uppercase;margin-bottom:10px">✦ AI Platform</div>
          <div style="font-size:38px;font-weight:800;color:var(--text-1);letter-spacing:-.02em;margin-bottom:8px">Andromeda</div>
          <div style="font-size:13px;color:var(--text-3)">{t('onb.initial')}</div>
        </div>

        {/* Steps indicator */}
        <div style="display:flex;align-items:center;justify-content:center;gap:8px;margin-bottom:36px">
          {[['install','Instalar Ollama'],['models','Descargar modelos'],['activate','Activar IAs']].map(([s, label], i) => {
            const steps = ['install','models','activate']
            const cur = steps.indexOf(step())
            const idx = steps.indexOf(s)
            const done = idx < cur
            const active = s === step()
            return (
              <div style="display:flex;align-items:center;gap:8px">
                {i > 0 && <div style={`width:40px;height:1px;background:${done?'var(--blue)':'var(--border)'}`} />}
                <div style={`display:flex;align-items:center;gap:6px;font-size:11px;font-weight:${active?'700':'400'};color:${active?'var(--blue)':done?'var(--green)':'var(--text-3)'}`}>
                  <div style={`width:20px;height:20px;border-radius:50%;border:1.5px solid ${active?'var(--blue)':done?'var(--green)':'var(--border)'};background:${active?'rgba(91,156,246,.12)':done?'rgba(52,211,153,.12)':'transparent'};display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700`}>
                    {done ? '✓' : String(i+1)}
                  </div>
                  <span style="white-space:nowrap">{label}</span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Step: Install Ollama */}
        <Show when={step() === 'install'}>
          <div class="card">
            <div class="card-title">1. {t('onb.install_title')}</div>
            <p style="font-size:13px;color:var(--text-2);line-height:1.7;margin-bottom:16px">
              {t('onb.install_desc')}
            </p>
            <a href="https://ollama.com/download" target="_blank"
              style="display:inline-flex;align-items:center;gap:8px;background:var(--blue);color:white;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">
              {t('onb.download_ollama')} ↗
            </a>
            <p style="font-size:11px;color:var(--text-3);margin-top:12px">
              {t('onb.install_hint')}
            </p>
            <Show when={checkError()}>
              <div style="margin-top:12px;padding:10px 14px;border-radius:8px;background:rgba(224,73,75,0.1);border:1px solid rgba(224,73,75,0.3);font-size:12px;color:var(--red)">
                ⚠️ {t('onb.ollama_not_found')}
                <Show when={diagInfo()}>
                  <div style="margin-top:6px;font-family:var(--mono);font-size:11px;color:var(--text-2);word-break:break-all">{diagInfo()}</div>
                </Show>
              </div>
            </Show>
            <div style="display:flex;gap:10px;margin-top:16px;align-items:center">
              <button class="btn btn-ghost" onClick={checkSetupWithError} disabled={checking()}>
                {checking() ? t('onb.checking') : t('onb.already_installed')}
              </button>
              <button class="btn btn-ghost" style="opacity:0.7" onClick={() => onDone?.()}>
                {t('onb.skip')}
              </button>
            </div>
          </div>
        </Show>

        {/* Step: Download models */}
        <Show when={step() === 'models'}>
          <div class="card">
            <div class="card-title">{t('onb.step2')}</div>
            <p style="font-size:13px;color:var(--text-2);line-height:1.7;margin-bottom:16px">
              {t('onb.models_hint')}
            </p>
            <For each={STARTER_MODELS}>
              {(m) => {
                const prog = () => pullProgress()[m.model]
                const isDone = () => prog()?.pct === 100
                const isError = () => prog()?.pct === -1
                const isActive = () => prog() && prog().pct >= 0 && prog().pct < 100
                return (
                  <div style="margin-bottom:12px;padding:12px 14px;background:var(--surface-2,rgba(255,255,255,.03));border:1px solid var(--hairline,rgba(255,255,255,.07));border-radius:10px">
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
                      <div style="min-width:0">
                        <div style="font-family:var(--mono);font-size:13px;color:var(--text-1);font-weight:600">{m.model}</div>
                        <div style="font-size:11px;color:var(--text-3)">{m.role} · {m.size}</div>
                      </div>
                      <button class="btn btn-primary" style="flex-shrink:0;font-size:12px;padding:6px 14px"
                        disabled={isActive() || isDone()}
                        onClick={() => downloadModel(m.model)}>
                        {isDone() ? t('onb.downloaded') : isActive() ? `${prog().pct}%` : isError() ? t('onb.retry') : t('onb.download')}
                      </button>
                    </div>
                    <Show when={isActive() || isDone()}>
                      <div style="margin-top:8px;height:6px;background:var(--hairline,rgba(255,255,255,.1));border-radius:99px;overflow:hidden">
                        <div style={`height:100%;width:${prog()?.pct || 0}%;background:var(--grad-primary);border-radius:99px;transition:width .4s ease`} />
                      </div>
                      <Show when={prog()?.total_mb > 0}>
                        <div style="font-size:10px;color:var(--text-3);margin-top:4px;font-family:var(--mono)">
                          {Math.round(prog().done_mb)} / {Math.round(prog().total_mb)} MB
                        </div>
                      </Show>
                    </Show>
                    <Show when={isError()}>
                      <div style="font-size:11px;color:var(--red,#f87171);margin-top:6px">{t('onb.dl_error')}</div>
                    </Show>
                  </div>
                )
              }}
            </For>
            <details style="margin-top:8px">
              <summary style="font-size:11px;color:var(--text-3);cursor:pointer">{t('onb.prefer_terminal')}</summary>
              <div style="margin-top:8px">
                <For each={STARTER_MODELS}>
                  {(m) => <div style="margin-bottom:6px">{CMD(`ollama pull ${m.model}`, m.model)}</div>}
                </For>
              </div>
            </details>
            <button class="btn btn-primary" style="margin-top:16px" onClick={checkSetup} disabled={checking()}>
              {checking() ? t('onb.checking') : t('onb.continue')}
            </button>
          </div>
        </Show>

        {/* Step: Activate specialists */}
        <Show when={step() === 'activate'}>
          <div class="card">
            <div class="card-title">{t('onb.step3')}</div>
            <p style="font-size:13px;color:var(--text-2);line-height:1.7;margin-bottom:16px">
              Ve a <strong>{t('ui2.ai_models')}</strong> en el menú lateral y asigna los modelos descargados a cada especialista.
            </p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              {[
                ['Orquestador', 'phi3.5:3.8b'],
                ['Generalist', 'mistral:7b'],
                ['SW Engineering', 'qwen2.5-coder:7b'],
                ['Verifier', 'phi3.5:3.8b'],
              ].map(([role, model]) => (
                <div style="padding:8px 12px;background:var(--surface);border:1px solid var(--border);border-radius:6px;font-size:11px">
                  <div style="font-weight:600;color:var(--text-1);margin-bottom:2px">{role}</div>
                  <div style="color:var(--text-3);font-family:var(--mono)">{model}</div>
                </div>
              ))}
            </div>
            <button class="btn btn-primary" style="margin-top:20px" onClick={() => { onDone?.() }}>
              Ir a la app →
            </button>
          </div>
        </Show>

        {/* Loading */}
        <Show when={step() === 'check'}>
          <div style="text-align:center;padding:40px;color:var(--text-3)">
            <span class="spin" style="width:24px;height:24px;border-width:2px" />
            <div style="margin-top:12px;font-size:13px">{t('onb.checking')}</div>
          </div>
        </Show>

      </div>
    </div>
  )
}
