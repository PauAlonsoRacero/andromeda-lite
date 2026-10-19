import { createSignal, Show } from 'solid-js'
import { chatState } from '../stores/chat.js'
import { t } from '../stores/i18n.js'


/** Latencia legible: "850ms" pero "12.3s" cuando pasa del segundo. */
function fmtMs(ms) {
  if (ms == null) return '—'
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
}

export default function TraceViewer() {
  const [open, setOpen] = createSignal(false)

  const trace = () => {
    const msgs = chatState.messages
    const last = msgs.filter(m => m.role === 'assistant' && m.metadata).at(-1)
    return last?.metadata || null
  }

  // <Show> en vez de "if (!trace()) return null": un componente de Solid se
  // ejecuta una sola vez, así que con el return temprano, si al montarse no
  // había traza aún, el panel no aparecía nunca aunque llegara después.
  return (
    <Show when={trace()}>
    <div class="trace-panel">
      <div class="trace-head" onClick={() => setOpen(v => !v)}>
        <div class="trace-head-left">
          <span>◈</span>
          <span>{t('trace.last')}</span>
          <Show when={trace()?.strategy_used}>
            <span style="color:var(--blue);font-family:var(--mono)">{trace().strategy_used}</span>
          </Show>
          <Show when={trace()?.degraded}>
            <span style="color:var(--amber)">⚠ {t('trace.degraded')}</span>
          </Show>
        </div>
        <span style="font-size:var(--fs-micro);color:var(--text-3)">{open() ? '▴' : '▾'}</span>
      </div>

      <Show when={open() && trace()}>
        <div class="trace-body">
          <div class="trace-row">
            <span class="trace-k">Estrategia</span>
            <span class="trace-v">{trace().strategy_used || '—'}</span>
          </div>
          <div class="trace-row">
            <span class="trace-k">Especialistas</span>
            <span class="trace-v">{trace().specialists_used?.join(', ') || '—'}</span>
          </div>
          <div class="trace-row">
            <span class="trace-k">Latencia</span>
            <span class={`trace-v ${trace().latency_ms > 20000 ? 'trace-warn' : 'trace-ok'}`}>
              {fmtMs(trace().latency_ms)}
            </span>
          </div>
          <div class="trace-row">
            <span class="trace-k">TTFT</span>
            <span class="trace-v">{fmtMs(trace().ttft_ms)}</span>
          </div>
          <div class="trace-row">
            <span class="trace-k">Tier</span>
            <span class="trace-v">T{trace().hardware_tier ?? '?'}</span>
          </div>
          <Show when={trace()?.degradation_reason}>
            <div class="trace-row">
              <span class="trace-k">{t('trace.degradation')}</span>
              <span class="trace-v trace-warn">{trace().degradation_reason?.slice(0,60)}</span>
            </div>
          </Show>
          <Show when={trace()?.routing_reasoning}>
            <div class="trace-reason">
              <div class="trace-reason-label">{t('ui2.orch_reasoning')}</div>
              <div class="trace-reason-text">{trace().routing_reasoning}</div>
            </div>
          </Show>
        </div>
      </Show>
    </div>
    </Show>
  )
}
