import { createSignal, Show } from 'solid-js'
import { chatState } from '../stores/chat.js'
import { t } from '../stores/i18n.js'

export default function TraceViewer() {
  const [open, setOpen] = createSignal(false)

  const trace = () => {
    const msgs = chatState.messages
    const last = msgs.filter(m => m.role === 'assistant' && m.metadata).at(-1)
    return last?.metadata || null
  }

  if (!trace()) return null

  return (
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
        <span style="font-size:10px;color:var(--text-3)">{open() ? '▴' : '▾'}</span>
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
              {trace().latency_ms ? Math.round(trace().latency_ms) + 'ms' : '—'}
            </span>
          </div>
          <div class="trace-row">
            <span class="trace-k">TTFT</span>
            <span class="trace-v">{trace().ttft_ms ? Math.round(trace().ttft_ms) + 'ms' : '—'}</span>
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
  )
}
