/**
 * ContextPanel.jsx — Pipeline de contexto de proyecto.
 * Indexa un proyecto de código y permite hacer preguntas sobre él.
 */
import { createSignal, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

export default function ContextPanel() {
  const [path, setPath]         = createSignal('')
  const [indexing, setIndexing] = createSignal(false)
  const [indexed, setIndexed]   = createSignal(null)
  const [question, setQuestion] = createSignal('')
  const [answer, setAnswer]     = createSignal(null)
  const [asking, setAsking]     = createSignal(false)
  const [error, setError]       = createSignal(null)

  async function indexProject() {
    if (!path().trim()) return
    setIndexing(true); setError(null); setIndexed(null)
    try {
      const r = await axios.post('/api/context/index', { path: path() })
      setIndexed(r.data)
    } catch (e) {
      setError(e.response?.data?.error || e.message)
    }
    setIndexing(false)
  }

  async function askQuestion() {
    if (!question().trim()) return
    setAsking(true); setAnswer(null)
    try {
      const r = await axios.post('/api/context/query', { question: question() })
      setAnswer(r.data)
    } catch (e) {
      setError(e.response?.data?.error || e.message)
    }
    setAsking(false)
  }

  async function clearContext() {
    await axios.delete('/api/context')
    setIndexed(null); setAnswer(null); setPath('')
  }

  const EXAMPLE_QUESTIONS = [
    '¿Qué hace este proyecto?',
    '¿Cuál es la arquitectura del sistema?',
    '¿Dónde se manejan los errores?',
    '¿Cómo se conecta con la base de datos?',
    '¿Qué tests existen?',
    'Genera un README completo para este proyecto',
  ]

  return (
    <div class="panel-page">
      <div class="panel-page-header">
        <div>
          <div class="panel-page-title">{t('ui2.proj_context')}</div>
          <div class="panel-page-sub">
            {t('ctx.subtitle')}
          </div>
        </div>
        <Show when={indexed()}>
          <button class="btn btn-danger" onClick={clearContext}>{t('ui2.clear_context')}</button>
        </Show>
      </div>

      <Show when={error()}>
        <div class="banner banner-error">{error()}</div>
      </Show>

      {/* Indexar proyecto */}
      <Show when={!indexed()}>
        <div class="card">
          <div class="card-title">{t('ui2.index_project')}</div>
          <div style="font-size:13px;color:var(--text-2);margin-bottom:14px;line-height:1.7">
            {t('ctx.index_desc')}
          </div>
          <div style="display:flex;gap:8px">
            <input
              class="g-input"
              value={path()}
              onInput={e => setPath(e.target.value)}
              placeholder={t('ctx.ph_path')}
              onKeyDown={e => e.key === 'Enter' && indexProject()}
              style="flex:1"
            />
            <button class="btn btn-primary" onClick={indexProject} disabled={indexing() || !path().trim()}>
              <Show when={indexing()} fallback={t('ctx.index_btn')}>
                <span class="spin" style="width:12px;height:12px;border-width:2px" /> {t('ctx.indexing')}
              </Show>
            </button>
          </div>
          <div style="font-size:11px;color:var(--text-3);margin-top:8px">
            {t('ctx.index_note')}
          </div>
        </div>
      </Show>

      {/* Proyecto indexado */}
      <Show when={indexed()}>
        <div class="card" style="background:rgba(52,211,153,.04);border-color:rgba(52,211,153,.2)">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:24px">📂</span>
            <div style="flex:1">
              <div style="font-size:14px;font-weight:700;color:var(--text-1)">{indexed().project}</div>
              <div style="font-size:12px;color:var(--text-3);margin-top:2px">
                {indexed().files_indexed} archivos · ~{indexed().total_tokens?.toLocaleString()} tokens
                <Show when={indexed().skipped_count > 0}>
                  {' · '}{indexed().skipped_count} omitidos
                </Show>
              </div>
            </div>
            <span style="color:var(--green);font-size:12px;font-weight:600">✓ Indexado</span>
          </div>
        </div>

        {/* Preguntas rápidas */}
        <div class="card">
          <div class="card-title">{t('ui2.proj_questions')}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
            {EXAMPLE_QUESTIONS.map(q => (
              <button
                class="quick-btn"
                onClick={() => { setQuestion(q); }}
                style="font-size:11px"
              >
                {q}
              </button>
            ))}
          </div>
          <div style="display:flex;gap:8px">
            <textarea
              class="g-input"
              value={question()}
              onInput={e => setQuestion(e.target.value)}
              placeholder={t('ctx.ph_question')}
              rows={3}
              style="flex:1;resize:vertical"
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askQuestion() } }}
            />
          </div>
          <button
            class="btn btn-primary"
            onClick={askQuestion}
            disabled={asking() || !question().trim()}
            style="margin-top:8px"
          >
            <Show when={asking()} fallback="Preguntar con contexto del proyecto">
              <span class="spin" style="width:12px;height:12px;border-width:2px" /> Analizando...
            </Show>
          </button>
        </div>

        <Show when={answer()}>
          <div class="card">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
              <div class="card-title" style="margin-bottom:0">Respuesta</div>
              <span style="font-size:10px;color:var(--text-3);font-family:var(--mono)">
                {answer().files_used} archivos · ~{answer().tokens_sent?.toLocaleString()} tokens · {answer().model}
              </span>
            </div>
            <div style="font-size:13px;color:var(--text-1);line-height:1.8;white-space:pre-wrap">
              {answer().response}
            </div>
          </div>
        </Show>
      </Show>
    </div>
  )
}
