/**
 * ChatSettings.jsx — Selector de IAs y potencia, rediseñado.
 *
 * Objetivo: que se entienda de un vistazo.
 *  - Arriba: cuántas IAs en paralelo (1–4) con su coste de VRAM.
 *  - Abajo: cada especialista con un punto de estado, su modelo resuelto,
 *    y un control de potencia compacto Auto · LOW · MID · HIGH · ULTRA.
 *  - Un único botón "Aplicar" cuando hay cambios.
 */
import { createSignal, onMount, For, Show } from 'solid-js'
import { hardware } from '../stores/hardware.js'
import { isPro } from '../stores/edition.js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import { supportsTools } from '../stores/modelCaps.js'

const LEVELS = [
  { id: 'auto',  label: 'Auto',  hint: null },  // hint traducido en render: cs.lvl_auto_hint
  { id: 'low',   label: 'Low',   hint: '~6B'  },
  { id: 'mid',   label: 'Mid',   hint: '~14B' },
  { id: 'high',  label: 'High',  hint: '~32B' },
  { id: 'ultra', label: 'Ultra', hint: '~70B' },
]

const SPECIALISTS = [
  { id: 'software-engineering', label: 'SW Engineering' },
  { id: 'generalist',           label: 'Generalist' },
  { id: 'it-ops',               label: 'IT Ops' },
  { id: 'technical-writer',     label: 'Technical Writer' },
  { id: 'verifier',             label: 'Verifier' },
  { id: 'summarizer',           label: 'Summarizer' },
]

export default function ChatSettings(props) {
  const onChange = props.onChange
  const [maxParallel, setMaxParallel] = createSignal(null)    // null = auto
  const [levelOverrides, setLevelOverrides] = createSignal({})
  const [vramPlan, setVramPlan] = createSignal(null)
  const [levelData, setLevelData] = createSignal({})
  const [dirty, setDirty] = createSignal(false)

  onMount(async () => {
    try {
      const [planRes, ...levelRes] = await Promise.allSettled([
        axios.get('/api/health/vram-plan'),
        ...SPECIALISTS.map(s => axios.get(`/api/models/levels/${s.id}`).catch(() => null)),
      ])
      if (planRes.status === 'fulfilled') setVramPlan(planRes.value.data)
      const lvlMap = {}
      SPECIALISTS.forEach((s, i) => {
        const r = levelRes[i]
        if (r?.status === 'fulfilled' && r.value?.data) lvlMap[s.id] = r.value.data
      })
      setLevelData(lvlMap)
    } catch {}
  })

  function notify(newParallel, newLevels) {
    onChange?.({
      parallel_policy:   newParallel === null ? 'auto' : 'max_hardware',
      max_parallel:      newParallel,
      specialist_levels: newLevels,
    })
  }

  function resolvedModel(specId) {
    const ld = levelData()[specId]
    if (!ld) return '—'
    const ov = levelOverrides()[specId]
    const lvl = ov || ld.auto_level || ld.current_level || 'mid'
    const m = ld.levels?.[lvl]?.model_name
    if (m) return m
    for (const k of ['low','mid','high','ultra']) {
      if (ld.levels?.[k]?.model_name) return ld.levels[k].model_name
    }
    return '—'
  }

  function setN(n) {
    setMaxParallel(n === maxParallel() ? null : n)
    setDirty(true)
  }
  function setLevel(specId, level) {
    const next = { ...levelOverrides(), [specId]: level === 'auto' ? undefined : level }
    Object.keys(next).forEach(k => next[k] === undefined && delete next[k])
    setLevelOverrides(next)
    setDirty(true)
    // En Lite no hay botón "Aplicar": el cambio de potencia surte efecto al instante.
    if (!isPro()) {
      notify(maxParallel(), next)
      setDirty(false)
    }
  }
  function applyChanges() {
    notify(maxParallel(), levelOverrides())
    setDirty(false)
    props.onApplied?.()
  }
  function resetAll() {
    setMaxParallel(null)
    setLevelOverrides({})
    setDirty(true)
  }

  const vram = () => vramPlan()?.vram_free_gb ?? null
  const hwTier = () => hardware()?.max_tier ?? 1
  const hwMaxParallel = () => vramPlan()?.max_parallel_policy ?? hardware()?.max_tier ?? 1
  const nFits = (n) => {
    const plan = vramPlan()?.plans?.[String(n)]
    if (!plan) return n <= (hardware()?.max_tier ?? 1)
    return plan.feasible
  }
  const levelAvailable = (specId, lvl) => {
    if (lvl === 'auto') return true
    const ld = levelData()[specId]
    // Si aún no tenemos datos del backend, permitimos el nivel (no bloqueamos al usuario).
    if (!ld?.levels?.[lvl]) return true
    return ld.levels[lvl].available !== false
  }
  const specActive = (specId) => {
    const ld = levelData()[specId]
    return ld ? (ld.active !== false) : true
  }

  return (
    <div class="ias-config">

      {/* ── LITE: orquestación lineal, una IA con power-scaling ── */}
      <Show when={!isPro()}>
        <div class="ias-block" style="margin:0">
          <div class="ias-seg ias-seg-power">
            <For each={LEVELS}>
              {(lvl) => {
                const on = () => (levelOverrides()['generalist'] || 'auto') === lvl.id
                const dis = () => !levelAvailable('generalist', lvl.id)
                return (
                  <button
                    class="ias-seg-btn"
                    classList={{ on: on(), dis: dis() }}
                    disabled={dis()}
                    onClick={() => !dis() && setLevel('generalist', lvl.id)}
                    title={dis() ? `${lvl.label} · ${t('cs.lvl_na_hw')}` : `${lvl.label} · ${lvl.hint || t('cs.lvl_auto_hint')}`}
                  >
                    {lvl.label}
                  </button>
                )
              }}
            </For>
          </div>
          <div class="ias-hint" style="margin-top:10px">
            <Show when={vram() !== null}><b style="color:var(--text-2)">{vram().toFixed(1)} {t('cs.gb_free')}</b> </Show>
            <b style="color:var(--text-2)">Auto</b> · {t('cs.power_auto_hint')}
          </div>

          {/* Selector de modelo concreto (antes estaba suelto en la barra inferior) */}
          <Show when={(props.ollamaModels || []).length > 0}>
            <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--hairline)">
              <div style="font-size:12px;color:var(--text-3);margin-bottom:7px">{t('chat.force_model')}</div>
              <select
                onChange={(e) => props.setForceModel?.(e.currentTarget.value)}
                style={`width:100%;font-size:13px;padding:8px 10px;border-radius:9px;background:var(--inset-surface);color:${props.forceModel ? 'var(--text-1)' : 'var(--text-3)'};border:1px solid var(--glass-border);cursor:pointer`}
              >
                <option value="" selected={!props.forceModel}>{t('chat.auto_power')}</option>
                <For each={props.ollamaModels || []}>
                  {(m) => <option value={m} selected={props.forceModel === m}>{supportsTools(m) ? '🔧 ' : ''}{m}</option>}
                </For>
              </select>
            </div>
          </Show>
        </div>
      </Show>

      {/* ── PRO: orquestación multi-IA en paralelo ── */}
      <Show when={isPro()}>
      <div class="ias-block">
        <div class="ias-block-head">
          <span class="ias-block-title">{t('cs.parallel_title')}</span>
          <span class="ias-block-meta">
            <Show when={vram() !== null}>{vram().toFixed(1)} {t('cs.gb_free_short')}</Show>
          </span>
        </div>

        <div class="ias-parallel">
          <For each={[1,2,3,4]}>
            {(n) => {
              const active   = () => maxParallel() === n
              const isAuto   = () => maxParallel() === null
              const tooMany  = () => n > hwMaxParallel()
              const disabled = () => !nFits(n) || tooMany()
              const plan     = () => vramPlan()?.plans?.[String(n)]
              return (
                <button
                  class="ias-parallel-btn"
                  classList={{ active: active(), auto: isAuto(), disabled: disabled() }}
                  disabled={disabled()}
                  onClick={() => !disabled() && setN(n)}
                  title={
                    disabled()
                      ? (tooMany()
                          ? `Tu hardware (T${hwTier()}) admite máx. ${hwMaxParallel()} IAs`
                          : `Sin VRAM para ${n} IAs`)
                      : `Usar ${n} IA${n>1?'s':''}`
                  }
                >
                  <span class="ias-parallel-n">{n}</span>
                  <span class="ias-parallel-cap">
                    <Show when={plan()?.vram_needed_gb && !disabled()} fallback={n > 1 ? `${n} IAs` : '1 IA'}>
                      {plan().vram_needed_gb.toFixed(0)} GB
                    </Show>
                  </span>
                </button>
              )
            }}
          </For>
        </div>
        <div class="ias-hint">
          <Show when={maxParallel() === null} fallback={`Fijado a ${maxParallel()} IA${maxParallel()>1?'s':''}.`}>
            Automático — el sistema usa las que caben según tu VRAM en cada momento.
          </Show>
        </div>
      </div>
      </Show>

      {/* ── Especialistas (solo Pro) ── */}
      <Show when={isPro()}>
      <div class="ias-block">
        <div class="ias-block-head">
          <span class="ias-block-title">{t('ui2.power_by_spec')}</span>
          <button class="ias-reset" onClick={resetAll}>{t('cs.reset')}</button>
        </div>

        <div class="ias-spec-list">
          <For each={SPECIALISTS}>
            {(spec) => {
              const override = () => levelOverrides()[spec.id] || 'auto'
              const active = () => specActive(spec.id)
              return (
                <div class="ias-spec" classList={{ inactive: !active() }}>
                  <div class="ias-spec-id">
                    <span class="ias-dot" classList={{ on: active() }} />
                    <div class="ias-spec-text">
                      <span class="ias-spec-name">{spec.label}</span>
                      <span class="ias-spec-model" title={resolvedModel(spec.id)}>{resolvedModel(spec.id)}</span>
                    </div>
                  </div>
                  <div class="ias-seg">
                    <For each={LEVELS}>
                      {(lvl) => {
                        const on = () => override() === lvl.id
                        const dis = () => !levelAvailable(spec.id, lvl.id)
                        return (
                          <button
                            class="ias-seg-btn"
                            classList={{ on: on(), dis: dis() }}
                            disabled={dis()}
                            onClick={() => !dis() && setLevel(spec.id, lvl.id)}
                            title={dis() ? `${lvl.label} no disponible en tu hardware` : `${lvl.label} · ${lvl.hint}`}
                          >
                            {lvl.label}
                          </button>
                        )
                      }}
                    </For>
                  </div>
                </div>
              )
            }}
          </For>
        </div>
        <div class="ias-hint ias-legend">
          <span class="ias-dot on" /> modelo listo
          <span class="ias-dot" style="margin-left:12px" /> sin descargar
        </div>
      </div>
      </Show>

      {/* ── Aplicar ── */}
      <div class="ias-foot">
        <Show when={dirty()}><span class="ias-pending">{t('ui2.unsaved')}</span></Show>
        <button class="ias-apply" classList={{ ready: dirty() }} disabled={!dirty()} onClick={applyChanges}>
          {t('cs.apply')}
        </button>
      </div>
    </div>
  )
}
