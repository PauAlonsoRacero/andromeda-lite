/**
 * LabPanel.jsx — Laboratorio de IA (modo avanzado).
 * Fine-tuning ligero real vía Ollama Modelfile: parámetros, system prompt
 * y entrenamiento few-shot con ejemplos o datasets JSONL.
 */
import { createSignal, onMount, onCleanup, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

export default function LabPanel() {
  const [models, setModels] = createSignal([])
  const [jobs, setJobs] = createSignal([])
  const [loading, setLoading] = createSignal(true)
  const [note, setNote] = createSignal(null)

  // Formulario de fine-tuning
  const [baseModel, setBaseModel] = createSignal('')
  const [variantName, setVariantName] = createSignal('')
  const [system, setSystem] = createSignal('')
  const [temp, setTemp] = createSignal(0.7)
  const [topP, setTopP] = createSignal(0.9)
  const [topK, setTopK] = createSignal(40)
  const [repeatPenalty, setRP] = createSignal(1.1)
  const [numCtx, setNumCtx] = createSignal(4096)
  const [examples, setExamples] = createSignal([{ user: '', assistant: '' }])
  const [rawDataset, setRawDataset] = createSignal('')
  const [training, setTraining] = createSignal(false)
  // Avanzado
  const [showAdv, setShowAdv] = createSignal(false)
  const [numPredict, setNumPredict] = createSignal('')
  const [minP, setMinP] = createSignal('')
  const [repeatLastN, setRepeatLastN] = createSignal('')
  const [seed, setSeed] = createSignal('')
  const [stops, setStops] = createSignal('')
  // Probar / asignar
  const [specialists, setSpecialists] = createSignal([])
  const [testPrompt, setTestPrompt] = createSignal({})
  const [testResult, setTestResult] = createSignal({})
  const [assignTo, setAssignTo] = createSignal({})

  const PRESETS = [
    { name: '🎯 Preciso',     desc: 'Determinista, para código y datos', t: 0.2, p: 0.85, k: 20, rp: 1.15 },
    { name: '⚖️ Equilibrado', desc: 'Uso general',                        t: 0.7, p: 0.9,  k: 40, rp: 1.1 },
    { name: '🎨 Creativo',    desc: 'Escritura, brainstorming',           t: 1.1, p: 0.95, k: 60, rp: 1.05 },
  ]
  function applyPreset(pr) { setTemp(pr.t); setTopP(pr.p); setTopK(pr.k); setRP(pr.rp) }

  let pollTimer = null

  onMount(async () => {
    try {
      const r = await axios.get('/api/models/ollama')
      setModels((r.data.models || []).map(m => m.name || m))
    } catch { /* Ollama offline */ }
    try {
      const r = await axios.get('/api/lab/specialists')
      setSpecialists(r.data.specialists || [])
    } catch { /* sin registry */ }
    await refreshJobs()
    pollTimer = setInterval(refreshJobs, 4000)
    setLoading(false)
  })
  onCleanup(() => pollTimer && clearInterval(pollTimer))

  async function refreshJobs() {
    try {
      const r = await axios.get('/api/lab/jobs')
      setJobs(r.data.jobs || [])
    } catch { /* backend offline */ }
  }

  function addExample() { setExamples([...examples(), { user: '', assistant: '' }]) }
  function setEx(i, field, val) {
    const list = [...examples()]; list[i] = { ...list[i], [field]: val }; setExamples(list)
  }
  function removeEx(i) { setExamples(examples().filter((_, idx) => idx !== i)) }

  async function importDataset() {
    if (!rawDataset().trim()) return
    try {
      const r = await axios.post('/api/lab/parse-dataset', { raw: rawDataset(), format: 'jsonl' })
      const imported = r.data.examples || []
      if (imported.length) {
        setExamples([...examples().filter(e => e.user || e.assistant), ...imported])
        setNote({ ok: true, text: `✓ ${imported.length} ejemplos importados del dataset` })
        setRawDataset('')
      } else {
        setNote({ ok: false, text: 'No se detectaron ejemplos. Formato esperado: JSONL con {"prompt","response"} por línea.' })
      }
    } catch (e) { setNote({ ok: false, text: 'Error al parsear: ' + (e.response?.data?.error || e.message) }) }
  }

  async function train() {
    if (!baseModel()) { setNote({ ok: false, text: 'Selecciona un modelo base.' }); return }
    setTraining(true); setNote(null)
    try {
      const r = await axios.post('/api/lab/finetune', {
        base_model: baseModel(),
        variant_name: variantName(),
        system: system(),
        parameters: {
          temperature: temp(), top_p: topP(), top_k: topK(),
          repeat_penalty: repeatPenalty(), num_ctx: numCtx(),
          num_predict: numPredict() || null, min_p: minP() || null,
          repeat_last_n: repeatLastN() || null, seed: seed() || null,
        },
        stop: stops().split(',').map(s => s.trim()).filter(Boolean),
        examples: examples().filter(e => e.user.trim() && e.assistant.trim()),
      })
      setNote({ ok: true, text: r.data.message })
      await refreshJobs()
    } catch (e) {
      setNote({ ok: false, text: 'Error: ' + (e.response?.data?.error || e.message) })
    }
    setTraining(false)
  }

  async function deleteVariant(name) {
    try { await axios.delete(`/api/lab/variant/${encodeURIComponent(name)}`); await refreshJobs()
      setNote({ ok: true, text: `Variante ${name} eliminada` })
    } catch (e) { setNote({ ok: false, text: 'Error al eliminar: ' + e.message }) }
  }

  async function testVariant(name) {
    const prompt = (testPrompt()[name] || '').trim()
    if (!prompt) return
    setTestResult(p => ({ ...p, [name]: { loading: true } }))
    try {
      const r = await axios.post('/api/lab/test', { variant: name, prompt })
      setTestResult(p => ({ ...p, [name]: r.data }))
    } catch (e) {
      setTestResult(p => ({ ...p, [name]: { error: e.response?.data?.error || e.message } }))
    }
  }

  async function assignVariant(name) {
    const sid = assignTo()[name]
    if (!sid) return
    try {
      const r = await axios.post('/api/lab/assign', { variant: name, specialist_id: sid })
      setNote({ ok: true, text: r.data.message })
      const rs = await axios.get('/api/lab/specialists')
      setSpecialists(rs.data.specialists || [])
    } catch (e) {
      setNote({ ok: false, text: e.response?.data?.error || e.message })
    }
  }

  const Slider = (p) => (
    <div style="flex:1;min-width:150px">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-3);margin-bottom:4px">
        <span>{p.label}</span><span style="font-family:var(--mono);color:var(--text-2)">{p.value()}</span>
      </div>
      <input type="range" min={p.min} max={p.max} step={p.step} value={p.value()}
        onInput={e => p.set(parseFloat(e.target.value))} style="width:100%" />
    </div>
  )

  return (
    <div class="panel-page" style="max-width:860px">
      <div class="panel-page-header">
        <div>
          <div class="panel-page-title">🧪 Lab de IA</div>
          <div class="panel-page-sub">{t('lab.create_variants')}</div>
        </div>
      </div>

      <Show when={note()}>
        <div class={`ios-note ${note().ok ? 'ios-note-ok' : 'ios-note-err'} anim-slide`}>{note().text}</div>
      </Show>

      {/* 1. Modelo base */}
      <div class="card stagger">
        <div class="card-title">1 · Modelo base</div>
        <Show when={models().length > 0} fallback={
          <div style="font-size:13px;color:var(--text-3)">{t('ui2.lab_no_ollama')}</div>
        }>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <For each={models()}>
              {(m) => (
                <button class="anim-spring" onClick={() => setBaseModel(m)}
                  style={`padding:8px 14px;border-radius:12px;font-size:12px;font-family:var(--mono);cursor:pointer;transition:all 0.2s;border:1.5px solid ${baseModel()===m?'var(--blue)':'var(--glass-border)'};background:${baseModel()===m?'rgba(123,140,240,0.12)':'transparent'};color:${baseModel()===m?'var(--text-1)':'var(--text-3)'}`}>
                  {m}
                </button>
              )}
            </For>
          </div>
        </Show>
      </div>

      {/* 2. Identidad y parámetros */}
      <div class="card stagger">
        <div class="card-title">{t('lab.identity_params')}</div>
        <input value={variantName()} onInput={e => setVariantName(e.target.value)}
          placeholder={t('lab.ph_name')} class="g-input" style="width:100%;margin-bottom:12px" />
        <textarea value={system()} onInput={e => setSystem(e.target.value)}
          placeholder={t('lab.ph_system')}
          class="g-input" style="width:100%;min-height:80px;resize:vertical;margin-bottom:16px;font-family:var(--font);line-height:1.5" />
        {/* Presets de personalidad */}
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
          <For each={PRESETS}>
            {(pr) => (
              <button class="anim-spring" onClick={() => applyPreset(pr)} title={pr.desc}
                style="padding:8px 14px;border-radius:12px;font-size:12px;cursor:pointer;border:1.5px solid var(--glass-border);background:transparent;color:var(--text-2);transition:all 0.2s">
                {pr.name}
              </button>
            )}
          </For>
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
          <Slider label="Temperatura (creatividad)" min={0} max={2} step={0.05} value={temp} set={setTemp} />
          <Slider label="Top P" min={0} max={1} step={0.05} value={topP} set={setTopP} />
          <Slider label="Top K" min={1} max={100} step={1} value={topK} set={setTopK} />
          <Slider label="Repeat penalty" min={0.5} max={2} step={0.05} value={repeatPenalty} set={setRP} />
          <Slider label="Contexto (tokens)" min={512} max={131072} step={512} value={numCtx} set={setNumCtx} />
        </div>

        {/* Avanzado plegable */}
        <button onClick={() => setShowAdv(!showAdv())}
          style="margin-top:16px;background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;padding:0;display:flex;align-items:center;gap:6px">
          <span style={`display:inline-block;transition:transform 0.25s;transform:rotate(${showAdv() ? 90 : 0}deg)`}>▸</span>
          Parámetros avanzados
        </button>
        <Show when={showAdv()}>
          <div class="anim-slide" style="margin-top:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
            <div>
              <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">{t('lab.max_tokens')}</div>
              <input class="g-input" type="number" placeholder={t('lab.ph_auto')} value={numPredict()}
                onInput={e => setNumPredict(e.target.value)} style="width:100%" />
            </div>
            <div>
              <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Min P (0-1)</div>
              <input class="g-input" type="number" step="0.01" placeholder={t('lab.ph_auto')} value={minP()}
                onInput={e => setMinP(e.target.value)} style="width:100%" />
            </div>
            <div>
              <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">{t('lab.anti_repeat')}</div>
              <input class="g-input" type="number" placeholder={t('lab.ph_auto')} value={repeatLastN()}
                onInput={e => setRepeatLastN(e.target.value)} style="width:100%" />
            </div>
            <div>
              <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Seed (reproducibilidad)</div>
              <input class="g-input" type="number" placeholder={t('lab.ph_random')} value={seed()}
                onInput={e => setSeed(e.target.value)} style="width:100%" />
            </div>
            <div style="grid-column:1/-1">
              <div style="font-size:11px;color:var(--text-3);margin-bottom:4px">{t('lab.stop_seqs')}</div>
              <input class="g-input" placeholder={t('lab.ph_stop')} value={stops()}
                onInput={e => setStops(e.target.value)} style="width:100%" />
            </div>
          </div>
        </Show>
      </div>

      {/* 3. Entrenamiento con ejemplos */}
      <div class="card stagger">
        <div class="card-title">3 · Entrenamiento con ejemplos (few-shot)</div>
        <div style="font-size:12px;color:var(--text-3);margin-bottom:14px">
          Los ejemplos se hornean en el modelo: aprenderá a responder siguiendo estos patrones.
        </div>
        <For each={examples()}>
          {(ex, i) => (
            <div class="anim-slide" style="display:flex;gap:8px;margin-bottom:10px;align-items:flex-start">
              <textarea value={ex.user} onInput={e => setEx(i(), 'user', e.target.value)}
                placeholder={t('lab.ph_user_q')} class="g-input" style="flex:1;min-height:54px;resize:vertical;font-size:12px" />
              <textarea value={ex.assistant} onInput={e => setEx(i(), 'assistant', e.target.value)}
                placeholder={t('lab.ph_ideal_a')} class="g-input" style="flex:1;min-height:54px;resize:vertical;font-size:12px" />
              <button onClick={() => removeEx(i())} title={t('lab.remove')}
                style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:15px;padding:6px">✕</button>
            </div>
          )}
        </For>
        <button class="btn btn-ghost" onClick={addExample}>{t('lab.add_example')}</button>

        <div style="margin-top:18px;padding-top:16px;border-top:1px solid var(--glass-border)">
          <div style="font-size:12px;font-weight:700;margin-bottom:8px">{t('ui2.import_dataset')}</div>
          <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">
            Pega un dataset de internet (HuggingFace, Kaggle...) con una línea JSON por ejemplo: {`{"prompt": "...", "response": "..."}`}
          </div>
          <textarea value={rawDataset()} onInput={e => setRawDataset(e.target.value)}
            placeholder={'{"prompt": "¿Qué es Docker?", "response": "Docker es..."}\n{"prompt": "...", "response": "..."}'}
            class="g-input" style="width:100%;min-height:70px;resize:vertical;font-family:var(--mono);font-size:11px" />
          <button class="btn btn-glass" onClick={importDataset} style="margin-top:8px">↓ Importar ejemplos</button>
        </div>
      </div>

      {/* 4. Entrenar */}
      <div class="card stagger" style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap">
        <div style="font-size:12px;color:var(--text-3)">
          {examples().filter(e => e.user.trim() && e.assistant.trim()).length} ejemplos válidos · modelo: <span style="font-family:var(--mono);color:var(--text-2)">{baseModel() || '—'}</span>
        </div>
        <button class="btn btn-primary anim-spring" onClick={train} disabled={training() || !baseModel()}>
          {training() ? 'Entrenando...' : '⚗ Entrenar variante'}
        </button>
      </div>

      {/* Trabajos */}
      <div class="card stagger">
        <div class="card-title">{t('ui2.lab_variants')}</div>
        <Show when={jobs().length > 0} fallback={
          <div style="text-align:center;padding:28px;color:var(--text-3);font-size:13px">{t('lab.no_variants')}</div>
        }>
          <For each={jobs()}>
            {(j) => (<>
              <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;gap:12px">
                <div style="min-width:0">
                  <div style="font-family:var(--mono);font-size:12px;color:var(--text-1);overflow:hidden;text-overflow:ellipsis">{j.variant}</div>
                  <div style="font-size:11px;color:var(--text-3)">{j.base_model} · {j.n_examples} ejemplos · {j.progress}</div>
                </div>
                <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
                  <span style={`font-size:11px;font-weight:700;padding:4px 10px;border-radius:8px;${j.status==='finished'?'background:rgba(52,211,153,0.15);color:var(--green)':j.status==='failed'?'background:rgba(248,113,113,0.15);color:var(--red)':'background:rgba(251,191,36,0.15);color:var(--amber)'}`}>
                    {j.status === 'finished' ? '✓ Lista' : j.status === 'failed' ? '✗ Error' : '⟳ En curso'}
                  </span>
                  <Show when={j.status !== 'running'}>
                    <button onClick={() => deleteVariant(j.variant)} title={t('lab.delete_variant')}
                      style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">🗑</button>
                  </Show>
                </div>
              </div>
              <Show when={j.status === 'finished'}>
                <div class="anim-slide" style="padding:12px 0 16px;border-bottom:1px solid var(--glass-border)">
                  {/* Probar en vivo */}
                  <div style="display:flex;gap:8px;margin-bottom:10px">
                    <input class="g-input" placeholder={t('lab.ph_test')}
                      value={testPrompt()[j.variant] || ''}
                      onInput={e => setTestPrompt(p => ({ ...p, [j.variant]: e.target.value }))}
                      onKeyDown={e => e.key === 'Enter' && testVariant(j.variant)}
                      style="flex:1;font-size:12px" />
                    <button class="btn btn-glass" style="font-size:12px;padding:8px 14px"
                      disabled={testResult()[j.variant]?.loading}
                      onClick={() => testVariant(j.variant)}>
                      {testResult()[j.variant]?.loading ? '…' : '▶ Probar'}
                    </button>
                  </div>
                  <Show when={testResult()[j.variant] && !testResult()[j.variant].loading}>
                    <div style="background:rgba(255,255,255,0.03);border:1px solid var(--glass-border);border-radius:12px;padding:12px;font-size:12.5px;line-height:1.55;color:var(--text-2);margin-bottom:12px;white-space:pre-wrap;max-height:180px;overflow-y:auto">
                      {testResult()[j.variant].error
                        ? <span style="color:var(--red)">{testResult()[j.variant].error}</span>
                        : testResult()[j.variant].response}
                      <Show when={testResult()[j.variant].total_ms}>
                        <div style="font-size:10px;color:var(--text-3);margin-top:8px;font-family:var(--mono)">
                          {testResult()[j.variant].eval_count} tokens · {testResult()[j.variant].total_ms} ms
                        </div>
                      </Show>
                    </div>
                  </Show>
                  {/* Asignar a especialista */}
                  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                    <span style="font-size:12px;color:var(--text-3)">{t('ui2.use_as')}</span>
                    <select class="g-input" style="font-size:12px;flex:1;min-width:160px"
                      value={assignTo()[j.variant] || ''}
                      onChange={e => setAssignTo(p => ({ ...p, [j.variant]: e.target.value }))}>
                      <option value="">— elegir especialista —</option>
                      <For each={specialists()}>
                        {(s) => <option value={s.id}>{s.name}{s.override === j.variant ? ' (asignado ✓)' : ''}</option>}
                      </For>
                    </select>
                    <button class="btn btn-primary" style="font-size:12px;padding:8px 16px"
                      disabled={!assignTo()[j.variant]}
                      onClick={() => assignVariant(j.variant)}>Asignar</button>
                  </div>
                </div>
              </Show>
              <div style="border-bottom:1px solid var(--glass-border)" />
            </>)}
          </For>
          <div style="font-size:11px;color:var(--text-3);margin-top:12px">
            Las variantes terminadas aparecen en IAs → Asignación para usarlas como especialistas.
          </div>
        </Show>
      </div>
    </div>
  )
}
