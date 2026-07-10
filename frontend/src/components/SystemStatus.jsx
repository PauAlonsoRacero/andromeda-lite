/**
 * SystemStatus.jsx — Panel de diagnóstico del sistema.
 * Modal con estado completo: hardware, Ollama, modelos cargados, VRAM, etc.
 * Se abre desde la topbar.
 */
import { Portal } from 'solid-js/web'
import { createSignal, onMount, onCleanup, Show, For } from 'solid-js'
import axios from 'axios'
import { hardware, liveUsage, health, policy } from '../stores/hardware.js'
import { isPro } from '../stores/edition.js'
import { t } from '../stores/i18n.js'

function StatRow({ label, value, ok, warn }) {
  const color = ok === true ? 'var(--green)' : ok === false ? 'var(--red)' : warn ? 'var(--amber)' : 'var(--text-2)'
  return (
    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--hairline)">
      <span style="font-size:12px;color:var(--text-3)">{label}</span>
      <span style={`font-size:12px;font-family:var(--mono);color:${color}`}>{value}</span>
    </div>
  )
}

export default function SystemStatus({ onClose, closing }) {
  const [warmStatus, setWarmStatus] = createSignal(null)
  const [vramPlan, setVramPlan]     = createSignal(null)
  const [loading, setLoading]       = createSignal(true)

  async function refresh() {
    try {
      const [warm, vram] = await Promise.allSettled([
        axios.get('/api/models/warm-status'),
        axios.get('/api/health/vram-plan'),
      ])
      if (warm.status === 'fulfilled') setWarmStatus(warm.value.data)
      if (vram.status === 'fulfilled') setVramPlan(vram.value.data)
    } catch {}
    setLoading(false)
  }

  onMount(() => {
    refresh()
    const id = setInterval(refresh, 3000)   // monitorización en tiempo real
    onCleanup(() => clearInterval(id))
  })

  const hw  = hardware
  const live = liveUsage
  const hth = health
  const pol = policy

  return (
    <Portal>
    <div class={`sys-overlay${closing ? ' closing' : ''}`} onClick={onClose}>
      <div class="sys-modal" onClick={e => e.stopPropagation()}>
        <div class="settings-title">
          <span style="font-weight:700;font-size:15px">{t('sys.title')}</span>
          <button onClick={onClose} style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:18px">✕</button>
        </div>

        <Show when={loading()}>
          <div style="text-align:center;padding:30px;color:var(--text-3)">
            <span class="spin" /> Cargando diagnóstico...
          </div>
        </Show>

        <Show when={!loading()}>
          {/* Estado general */}
          <div class="settings-section">
            <div class="settings-section-title">{t('sys.general')}</div>
            <StatRow label={t('sys.lbl_system')}   value={hth()?.status === 'ok' ? 'ok' : t('sys.val_unknown')}  ok={hth()?.status === 'ok'} />
            <StatRow label="Ollama"    value={hth()?.ollama?.reachable ? t('sys.val_connected') : t('sys.val_offline')} ok={hth()?.ollama?.reachable} />
            <StatRow label={t('sys.lbl_backend')}   value="activo" ok={true} />
            <StatRow label={t('sys.lbl_tier')}   value={`T${hw()?.max_tier ?? '?'}`} />
          </div>

          {/* Hardware */}
          <Show when={hw()}>
            <div class="settings-section">
              <div class="settings-section-title">{t('sys.hardware')}</div>
              <StatRow label="CPU"      value={hw()?.cpu_model?.slice(0,30) || '—'} />
              <StatRow label={t('sys.lbl_cpu_cores')} value={hw()?.cpu_cores} />
              <StatRow label={t('sys.lbl_ram_total')} value={`${hw()?.ram_total_gb?.toFixed(1)} GB`} />
              <StatRow label={t('sys.lbl_ram_free')} value={`${hw()?.ram_available_gb?.toFixed(1)} GB`} />
              <StatRow label="GPU"      value={hw()?.gpus?.length > 0 ? hw().gpus[0].name : 'CPU only'} />
              <StatRow label="VRAM"     value={`${hw()?.total_vram_gb?.toFixed(1)} GB`} warn={hw()?.total_vram_gb < 8} />
              <StatRow label={t('sys.lbl_accel')} value={hw()?.acceleration?.toUpperCase()} />
            </div>
          </Show>

          {/* Memoria / VRAM en tiempo real (sondeo cada 4s vía /hardware/live) */}
          <Show when={live() || vramPlan() || hw()}>
            <div class="settings-section">
              <div class="settings-section-title">{t('sys.memory_rt')}</div>
              <Show when={(live()?.vram_free_gb ?? vramPlan()?.vram_free_gb) != null}>
                <StatRow label={t('sys.lbl_vram_free')}
                  value={`${(live()?.vram_free_gb ?? vramPlan()?.vram_free_gb)?.toFixed(1)} GB`}
                  ok={(live()?.vram_free_gb ?? vramPlan()?.vram_free_gb) > 2} />
              </Show>
              <Show when={live()?.vram_used_pct != null}>
                <StatRow label={t('sys.lbl_vram_used')} value={`${live()?.vram_used_pct?.toFixed(0)}%`}
                  warn={live()?.vram_used_pct > 85} />
              </Show>
              <Show when={(live()?.ram_available_gb ?? hw()?.ram_available_gb) != null}>
                <StatRow label={t('sys.lbl_ram_free')}
                  value={`${(live()?.ram_available_gb ?? hw()?.ram_available_gb)?.toFixed(1)} GB`} />
              </Show>
              <Show when={live()?.ram_used_pct != null}>
                <StatRow label={t('sys.lbl_ram_used')} value={`${live()?.ram_used_pct?.toFixed(0)}%`}
                  warn={live()?.ram_used_pct > 90} />
              </Show>
            </div>
          </Show>

          {/* Política activa — solo Pro (orquestación multi-IA) */}
          <Show when={pol() && isPro()}>
            <div class="settings-section">
              <div class="settings-section-title">{t('sys.policy')}</div>
              <StatRow label={t('sys.lbl_parallel_max')} value={pol()?.max_parallel} />
              <StatRow label={t('sys.lbl_quant')}  value={pol()?.recommended_quant} />
              <StatRow label={t('sys.lbl_ctx_max')}      value={`${pol()?.max_context_tokens?.toLocaleString()} tokens`} />
              <StatRow label={t('sys.lbl_verifier')} value={pol()?.can_run_verifier ? t('sys.val_yes') : t('sys.val_no')} ok={pol()?.can_run_verifier} />
            </div>
          </Show>

          {/* Modelos en VRAM */}
          <Show when={warmStatus()?.loaded_in_vram}>
            <div class="settings-section">
              <div class="settings-section-title">{t('sys.hot_models')}</div>
              <Show
                when={Object.keys(warmStatus().loaded_in_vram).length > 0}
                fallback={<div style="font-size:12px;color:var(--text-3);padding:6px 0">{t('sys.no_models')}</div>}
              >
                <For each={Object.entries(warmStatus().loaded_in_vram)}>
                  {([model, info]) => (
                    <StatRow
                      label={model}
                      value={`${info.size_mb} MB`}
                      ok={true}
                    />
                  )}
                </For>
              </Show>
            </div>
          </Show>

          {/* VRAM disponible para IAs — solo Pro (en Lite es 1 IA) */}
          <Show when={vramPlan() && isPro()}>
            <div class="settings-section">
              <div class="settings-section-title">{t('sys.parallel')}</div>
              <StatRow label={t('sys.lbl_vram_free')} value={`${vramPlan()?.vram_free_gb?.toFixed(1)} GB`} />
              <For each={['1','2','3','4']}>
                {(n) => {
                  const plan = vramPlan()?.plans?.[n]
                  return (
                    <StatRow
                      label={`${n} IA${n > '1' ? 's'  : ''} simultánea${n > '1' ? 's' : ''}`}
                      value={plan?.feasible ? `✓ ${plan.vram_needed_gb?.toFixed(1)}GB` : `✗ necesita ${plan?.vram_needed_gb?.toFixed(1)}GB`}
                      ok={plan?.feasible}
                    />
                  )
                }}
              </For>
            </div>
          </Show>

          {/* Links útiles — herramientas técnicas, solo Pro */}
          <Show when={isPro()}>
          <div class="settings-section">
            <div class="settings-section-title">{t('sys.shortcut')}</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;padding-top:4px">
              {[
                { label:'API Docs', url:'/docs' },
                { label:'Health', url:'/api/health' },
                { label:'MLOps', url:'/api/mlops/summary' },
                { label:'Traces', url:'/api/traces' },
              ].map(({ label, url }) => (
                <a
                  href={url}
                  target="_blank"
                  style="padding:5px 10px;border-radius:var(--r-xs);background:var(--hover-surface);border:1px solid var(--glass-border);color:var(--text-2);font-size:11px;text-decoration:none;transition:all .12s"
                  onMouseEnter={e => { e.currentTarget.style.background='var(--glass-hi)'; e.currentTarget.style.color='var(--text-1)' }}
                  onMouseLeave={e => { e.currentTarget.style.background='var(--hover-surface)'; e.currentTarget.style.color='var(--text-2)' }}
                >
                  {label} ↗
                </a>
              ))}
            </div>
          </div>
          </Show>
        </Show>
      </div>
    </div>
    </Portal>
  )
}
