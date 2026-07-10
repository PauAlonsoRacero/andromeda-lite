/**
 * ModelsPanel.jsx — Gestión de especialistas iOS 26.
 * Activar/desactivar IAs, asignar modelo de Ollama, ver info de cada una.
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import { refreshHardware } from '../stores/hardware.js'
import { isPro } from '../stores/edition.js'
import ModelExplorer from './ModelExplorer.jsx'
import { t } from '../stores/i18n.js'
import InfoButton from './InfoButton.jsx'

// Traduce los campos del especialista si hay clave i18n (p. ej. generalist).
function specField(spec, field, fallback) {
  const key = `spec.${spec?.id}.${field}`
  const v = t(key)
  return v === key ? (fallback || '') : v
}

export default function ModelsPanel() {
  const [view, setView]                 = createSignal('specialists')  // specialists | explore
  const [specialists, setSpecialists]   = createSignal([])
  const [ollamaModels, setOllamaModels] = createSignal([])
  const [ollamaOnline, setOllamaOnline] = createSignal(false)
  const [loading, setLoading]           = createSignal(true)
  const [busy, setBusy]                 = createSignal(null)
  const [msg, setMsg]                   = createSignal({})
  const [adding, setAdding]             = createSignal(false)

  onMount(loadData)

  async function loadData() {
    setLoading(true)
    try {
      const [specs, ollama] = await Promise.allSettled([
        axios.get('/api/models').then(r => r.data),
        axios.get('/api/models/ollama').then(r => r.data),
      ])
      if (specs.status === 'fulfilled') setSpecialists(specs.value.specialists || [])
      if (ollama.status === 'fulfilled') {
        setOllamaModels(ollama.value.models || [])
        setOllamaOnline(ollama.value.reachable !== false && (ollama.value.models || []).length >= 0)
        setOllamaOnline(ollama.value.reachable ?? true)
      }
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
    refreshHardware()
  }

  async function setModel(specId, modelName, active) {
    setBusy(specId)
    setMsg(m => ({ ...m, [specId]: null }))
    // Modelo que estaba asignado antes (para descargarlo si cambia o se desactiva)
    const prev = (specialists().find(s => s.id === specId) || {}).model_name
    try {
      await axios.put(`/api/models/${specId}`, { model_name: modelName, active })
      // Al DESACTIVAR, o al CAMBIAR de modelo, apagamos el anterior de la VRAM
      // (no debe quedarse caliente). El nuevo se cargará al primer uso.
      const toUnload = !active ? prev : (prev && prev !== modelName ? prev : null)
      if (toUnload) {
        try { await axios.post('/api/models/unload', { models: [toUnload] }) } catch {}
      }
      setMsg(m => ({ ...m, [specId]: active ? 'Aplicado' : 'Desactivado' }))
      await loadData()
      setTimeout(() => setMsg(m => ({ ...m, [specId]: null })), 2500)
    } catch (e) {
      const detail = e.response?.data?.message || e.message
      setMsg(m => ({ ...m, [specId]: 'Error: ' + detail }))
    } finally {
      setBusy(null)
    }
  }

  // En Lite el producto es UNA sola IA (el generalista) que escala de potencia.
  // Los demás especialistas son la orquestación multi-IA de Pro.
  const visibleSpecs = () => isPro() ? specialists() : specialists().filter(s => s.id === 'generalist')
  const active   = () => visibleSpecs().filter(s => s.active)
  const inactive = () => visibleSpecs().filter(s => !s.active)

  return (
    <div class="panel-page">
      <div class="panel-page-header">
        <div>
          <div style="display:flex;align-items:center;gap:9px"><div class="panel-page-title">{t('ui2.ai_models')}</div><InfoButton title={t('ui2.ai_models')} intro={t('info.mdl.intro')} tip={t('info.mdl.tip')} items={[
            { h: t('info.mdl.1h'), d: t('info.mdl.1d') },
            { h: t('info.mdl.2h'), d: t('info.mdl.2d') },
            { h: t('info.mdl.3h'), d: t('info.mdl.3d') },
            { h: t('info.mdl.4h'), d: t('info.mdl.4d') },
          ]} /></div>
          <div class="panel-page-sub">{t('mdl.activate')}</div>
        </div>
        <button class="btn btn-ghost" onClick={loadData} disabled={loading()}>
          {loading() ? <span class="spin" /> : '↺'} {t('common.refresh')}
        </button>
      </div>

      {/* Pestañas: Especialistas | Explorar modelos */}
      <div style="display:flex;gap:4px;background:var(--glass-bright);border-radius:12px;padding:4px;margin-bottom:20px;width:fit-content">
        <button onClick={() => setView('specialists')}
          style={`padding:8px 18px;border-radius:9px;border:none;cursor:pointer;font-size:13px;font-weight:600;font-family:var(--font);transition:all 0.15s;background:${view()==='specialists'?'var(--glass-hi)':'transparent'};color:${view()==='specialists'?'var(--text-1)':'var(--text-3)'}`}>
          {t('mdl.tab_specialists')}
        </button>
        <button onClick={() => setView('explore')}
          style={`padding:8px 18px;border-radius:9px;border:none;cursor:pointer;font-size:13px;font-weight:600;font-family:var(--font);transition:all 0.15s;background:${view()==='explore'?'var(--glass-hi)':'transparent'};color:${view()==='explore'?'var(--text-1)':'var(--text-3)'}`}>
          ⌕ {t('mdl.tab_explore')}
        </button>
      </div>

      <Show when={view() === 'explore'}>
        <ModelExplorer />
      </Show>

      <Show when={view() === 'specialists'}>
      {/* Estado Ollama */}
      <Show when={!ollamaOnline()}>
        <div class="banner banner-warn">
          <span style="font-size:16px">⚠️</span>
          <div>
            <div style="font-weight:700;margin-bottom:3px">{t('mdl.ollama_down')}</div>
            <div style="font-size:12px">{t('mdl.install_ollama')}<code style="font-family:var(--mono);background:var(--inset-surface);padding:2px 6px;border-radius:5px">ollama pull mistral:7b</code></div>
          </div>
        </div>
      </Show>

      <Show when={ollamaOnline()}>
        <div class="banner banner-ok">
          <span style="font-size:16px">✓</span>
          <div style="font-size:12px">
            <strong>{t('ui2.ollama_connected')}</strong> · {ollamaModels().length} {t('mdl.models_available')}
            <Show when={ollamaModels().length > 0}>
              <span style="color:var(--text-3)"> · {ollamaModels().map(m => typeof m === 'string' ? m : m.name).join(', ')}</span>
            </Show>
          </div>
        </div>
      </Show>

      {/* IAs ACTIVAS */}
      <div style="margin-bottom:10px;margin-top:24px;display:flex;align-items:center;gap:10px">
        <span style="width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green)" />
        <span style="font-size:13px;font-weight:700;color:var(--text-1)">{isPro() ? t('mdl.ais_active') : t('mdl.your_ai')}</span>
        <span style="font-size:12px;color:var(--text-3)">{active().length}</span>
      </div>

      <Show when={active().length > 0} fallback={
        <div class="card" style="text-align:center;padding:36px">
          <div style="font-size:15px;font-weight:600;margin-bottom:6px">{isPro() ? t('mdl.none_active') : t('mdl.your_ai_inactive')}</div>
          <div style="font-size:13px;color:var(--text-3);margin-bottom:20px">{isPro() ? 'Activa un especialista de la lista de abajo para empezar' : 'Asígnale un modelo de Ollama abajo para empezar a usar Andromeda'}</div>
        </div>
      }>
        <For each={active()}>
          {(s) => <SpecCard spec={s} ollamaModels={ollamaModels} ollamaOnline={ollamaOnline}
                            busy={busy()===s.id} msg={msg()[s.id]}
                            onActivate={(model) => setModel(s.id, model, true)}
                            onDeactivate={() => setModel(s.id, s.model_name, false)} />}
        </For>
      </Show>

      {/* IAs DISPONIBLES (inactivas) */}
      <div style="margin-bottom:10px;margin-top:28px;display:flex;align-items:center;gap:10px">
        <span style="font-size:13px;font-weight:700;color:var(--text-2)">{isPro() ? t('mdl.available_activate') : t('mdl.your_ai_unactivated')}</span>
        <span style="font-size:12px;color:var(--text-3)">{inactive().length}</span>
      </div>

      <div class="stagger" style="display:flex;flex-direction:column;gap:12px">
      <For each={inactive()}>
        {(s) => <SpecCard spec={s} ollamaModels={ollamaModels} ollamaOnline={ollamaOnline}
                          busy={busy()===s.id} msg={msg()[s.id]}
                          onActivate={(model) => setModel(s.id, model, true)}
                          onDeactivate={() => setModel(s.id, s.model_name, false)} />}
      </For>
      </div>
      </Show>
    </div>
  )
}

// ── Tarjeta de especialista ────────────────────────────────────────────────
function SpecCard(props) {
  const s = () => props.spec
  const [selectedModel, setSelectedModel] = createSignal(s().model_name)
  const [autoTier, setAutoTier] = createSignal(null)   // tier detectado en vivo
  const [detecting, setDetecting] = createSignal(false)

  // Cuando cambia el modelo seleccionado, detecta su tier automáticamente
  async function detectTier(modelName) {
    if (!modelName || modelName === 'PENDIENTE_CONFIGURAR') { setAutoTier(null); return }
    setDetecting(true)
    try {
      const r = await axios.post('/api/models/auto-classify', { model_name: modelName })
      setAutoTier(r.data)
    } catch (e) { setAutoTier(null) }
    setDetecting(false)
  }

  // Detecta al montar y cada vez que cambia la selección
  onMount(() => { detectTier(selectedModel()); loadRole() })
  function onModelChange(v) {
    setSelectedModel(v)
    detectTier(v)
  }

  // ── Rol/topic personalizado (especialización) ──
  const [showRole, setShowRole]       = createSignal(false)
  const [topic, setTopic]             = createSignal('')
  const [instructions, setInstructions] = createSignal('')
  const [roleSaved, setRoleSaved]     = createSignal(false)
  const [savedTopic, setSavedTopic]   = createSignal('')

  async function loadRole() {
    try {
      const r = await axios.get(`/api/models/role/${s().id}`)
      if (r.data.role) {
        setTopic(r.data.role.topic || '')
        setInstructions(r.data.role.instructions || '')
        setSavedTopic(r.data.role.topic || '')
      }
    } catch (e) {}
  }

  async function saveRole() {
    if (!topic().trim()) return
    try {
      await axios.put(`/api/models/role/${s().id}`, { topic: topic(), instructions: instructions() })
      setSavedTopic(topic())
      setRoleSaved(true)
      setTimeout(() => setRoleSaved(false), 2500)
    } catch (e) {}
  }

  async function clearRole() {
    try {
      await axios.delete(`/api/models/role/${s().id}`)
      setTopic(''); setInstructions(''); setSavedTopic('')
    } catch (e) {}
  }

  // ── Hornear identidad + topic en el modelo ──
  const [baking, setBaking]           = createSignal(false)
  const [bakedVariant, setBakedVariant] = createSignal('')

  async function bakeSpecialized() {
    setBaking(true)
    setBakedVariant('')
    try {
      const r = await axios.post('/api/models/bake-identity', {
        model_name: selectedModel(),
        topic: topic(),
        instructions: instructions(),
      })
      setBakedVariant(r.data.variant)
    } catch (e) {}
    setBaking(false)
  }

  const TIER_COLOR = { 1: 'var(--green)', 2: 'var(--blue)', 3: 'var(--purple)', 4: 'var(--pink)' }

  const ICONS = {
    'software-engineering': <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>,
    'generalist':           <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></svg>,
    'it-ops':               <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>,
    'technical-writer':     <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>,
    'verifier':             <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>,
    'summarizer':           <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="14" y2="18"/></svg>,
  }
  const fallbackIcon = <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/></svg>
  const modelList = () => props.ollamaModels().map(m => typeof m === 'string' ? m : m.name)

  return (
    <div class="card fade-up lift" style={`border-color:${s().active ? 'rgba(52,211,153,0.25)' : 'var(--glass-border)'}`}>
      <div style="display:flex;align-items:flex-start;gap:14px">
        {/* Icono */}
        <div class="app-icon" style={`width:48px;height:48px;font-size:20px;color:${s().active?'var(--green)':'var(--text-3)'};flex-shrink:0`}>
          {ICONS[s().id] || fallbackIcon}
        </div>

        {/* Info */}
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
            <span style="font-size:15px;font-weight:700">{specField(s(), "name", s().name)}</span>
            <span style={`font-size:10px;font-weight:700;padding:2px 8px;border-radius:7px;background:${s().active?'rgba(52,211,153,0.15)':'var(--chip-surface)'};color:${s().active?'var(--green)':'var(--text-3)'}`}>
              {s().active ? t('mdl.active') : t('mdl.inactive')}
            </span>
          </div>
          <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">{specField(s(), "desc", s().description || s().domain)}</div>

          {/* Campos de info — el Tier ahora se detecta en vivo */}
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:14px">
            <InfoField label={t("mdl.speciality")} value={specField(s(), "domain", s().domain) || '—'} />
            <InfoField label={t("mdl.vram_est")} value={autoTier() ? `${autoTier().vram_estimated_gb} GB` : `${(s().vram_required_gb || 0).toFixed(1)} GB`} />
            <div style="padding:8px 11px;background:var(--inset-surface);border-radius:10px;border:1px solid var(--glass-border)">
              <div style="font-size:9px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.05em">{t('mdl.tier_auto')}</div>
              <div style="font-size:12px;margin-top:2px;font-weight:700" class={detecting() ? '' : 'anim-spring'}>
                <Show when={!detecting()} fallback={<span style="color:var(--text-3)">detectando...</span>}>
                  <Show when={autoTier()} fallback={<span style="color:var(--text-3)">—</span>}>
                    <span style={`color:${TIER_COLOR[autoTier().tier]}`}>{autoTier().tier_name}</span>
                  </Show>
                </Show>
              </div>
            </div>
          </div>

          {/* Selector de modelo + acción */}
          <Show when={props.ollamaOnline()} fallback={
            <div style="font-size:12px;color:var(--text-3);font-style:italic">{t('mdl.connect_ollama')}</div>
          }>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <select
                class="g-input"
                value={selectedModel()}
                onChange={e => onModelChange(e.target.value)}
                style="flex:1;min-width:160px;cursor:pointer"
              >
                <Show when={!modelList().includes(selectedModel())}>
                  <option value={selectedModel()}>{selectedModel()} (no descargado)</option>
                </Show>
                <For each={modelList()}>
                  {(m) => <option value={m}>{m}</option>}
                </For>
              </select>

              <Show when={!s().active} fallback={
                <button class="btn btn-danger" onClick={props.onDeactivate} disabled={props.busy}>
                  {props.busy ? <span class="spin" /> : t('mdl.deactivate')}
                </button>
              }>
                <button class="btn btn-primary" onClick={() => props.onActivate(selectedModel())} disabled={props.busy}>
                  {props.busy ? <span class="spin" /> : 'Activar'}
                </button>
              </Show>
            </div>
            <Show when={props.msg}>
              <div style={`font-size:12px;margin-top:8px;color:${props.msg.startsWith('Error')?'var(--red)':'var(--green)'}`}>{props.msg}</div>
            </Show>

            {/* ── Especialización: asignar topic ── */}
            <div style="margin-top:14px;padding-top:14px;border-top:0.5px solid var(--glass-border)">
              <button onClick={() => setShowRole(!showRole())}
                style="display:flex;align-items:center;gap:8px;background:none;border:none;color:var(--text-2);font-size:13px;cursor:pointer;padding:0;font-weight:600;font-family:var(--font)">
                <span style={`transition:transform 0.3s cubic-bezier(0.34,1.56,0.64,1);display:inline-block;transform:rotate(${showRole()?'90':'0'}deg)`}>▸</span>
                {t('mdl.specialize_topic')}
                <Show when={savedTopic()}>
                  <span class="ios-tag" style="background:rgba(123,140,240,0.15);color:var(--blue)">{savedTopic()}</span>
                </Show>
              </button>

              <Show when={showRole()}>
                <div class="anim-slide" style="margin-top:12px;display:flex;flex-direction:column;gap:10px">
                  <div>
                    <label style="font-size:11px;color:var(--text-3);font-weight:700;text-transform:uppercase;letter-spacing:0.04em;display:block;margin-bottom:5px">{t('mdl.topic_domain')}</label>
                    <input class="g-input" value={topic()} onInput={e => setTopic(e.target.value)}
                      placeholder={t('mdl.ph_topic')}
                      style="width:100%" />
                  </div>
                  <div>
                    <label style="font-size:11px;color:var(--text-3);font-weight:700;text-transform:uppercase;letter-spacing:0.04em;display:block;margin-bottom:5px">{t('mdl.specific_instr')}</label>
                    <textarea class="g-input" value={instructions()} onInput={e => setInstructions(e.target.value)}
                      placeholder={t('mdl.ph_instr')}
                      style="width:100%;min-height:64px;resize:vertical;font-family:var(--font)" />
                  </div>
                  <div style="display:flex;gap:8px;align-items:center">
                    <button class="btn btn-primary" style="font-size:13px;padding:8px 16px" onClick={saveRole} disabled={!topic().trim()}>
                      Guardar especialización
                    </button>
                    <Show when={savedTopic()}>
                      <button class="btn btn-ghost" style="font-size:13px;padding:8px 14px" onClick={clearRole}>{t('mdl.remove')}</button>
                    </Show>
                    <Show when={roleSaved()}>
                      <span class="anim-spring" style="font-size:12px;color:var(--green);font-weight:600">✓ Guardado</span>
                    </Show>
                  </div>

                  {/* Hornear la especialización en el modelo (Modelfile) */}
                  <Show when={savedTopic() && props.ollamaOnline()}>
                    <div style="margin-top:6px;padding-top:10px;border-top:0.5px solid var(--glass-border)">
                      <button class="btn btn-glass" style="font-size:13px;padding:8px 16px"
                        disabled={baking()}
                        onClick={bakeSpecialized}
                        title={t('mdl.variant_hint')}>
                        <Show when={!baking()} fallback={<><span class="spin" /> Horneando...</>}>⚙ {t('mdl.record_spec')}</Show>
                      </button>
                      <Show when={bakedVariant()}>
                        <div class="ios-note ios-note-ok anim-spring" style="margin-top:8px">
                          Variante creada: <b style="font-family:var(--font-mono)">{bakedVariant()}</b>.
                          Cuando termine de crearse, selecciónala arriba en el desplegable y pulsa Activar. El topic queda horneado dentro.
                        </div>
                      </Show>
                      <div style="font-size:11px;color:var(--text-3);margin-top:6px;line-height:1.4">
                        Diferencia: t('mdl.save_spec') se aplica al instante vía prompt. "Grabar en el modelo" crea una variante permanente con el topic horneado — más difícil de que se desvíe.
                      </div>
                    </div>
                  </Show>
                  <div style="font-size:11px;color:var(--text-3);line-height:1.4">
                    {t('mdl.topic_applies')}
                  </div>
                </div>
              </Show>
            </div>
          </Show>
        </div>
      </div>
    </div>
  )
}

function InfoField(props) {
  return (
    <div style="padding:8px 11px;background:var(--inset-surface);border-radius:10px;border:1px solid var(--glass-border)">
      <div style="font-size:9px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.05em">{props.label}</div>
      <div style="font-size:12px;color:var(--text-2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{props.value}</div>
    </div>
  )
}
