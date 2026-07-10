/**
 * StatsPanel.jsx — Estadísticas + MLOps con gráficos SVG nativos.
 * Tres pestañas: Actividad · Rendimiento · Proyecciones.
 */
import { createSignal, onMount, For, Show, createMemo } from 'solid-js'
import axios from 'axios'
import { LineChart, Sparkline, BarSeries, Donut, GaugeRing } from './charts/Charts.jsx'
import { t } from '../stores/i18n.js'

export default function StatsPanel() {
  const [tab, setTab]       = createSignal('activity')
  const [kpis, setKpis]     = createSignal(null)
  const [traces, setTraces] = createSignal([])
  const [mlops, setMlops]   = createSignal(null)
  const [drift, setDrift]   = createSignal(null)
  const [pct, setPct]       = createSignal(null)
  const [throughput, setTp] = createSignal(null)
  const [series, setSeries] = createSignal([])
  const [runs, setRuns]     = createSignal([])
  const [modelsUsed, setModelsUsed] = createSignal([])
  const [errors, setErrors] = createSignal(null)
  const [loading, setLoading] = createSignal(true)

  onMount(loadAll)

  async function loadAll() {
    setLoading(true)
    const [m, t, ml, r] = await Promise.allSettled([
      axios.get('/api/traces/metrics').then(x => x.data),
      axios.get('/api/traces?limit=25').then(x => x.data),
      axios.get('/api/mlops/summary').then(x => x.data),
      axios.get('/api/mlops/runs').then(x => x.data),
    ])
    if (m.status === 'fulfilled')  setKpis(m.value?.realtime || {})
    if (t.status === 'fulfilled')  setTraces(t.value.traces || [])
    if (ml.status === 'fulfilled') setMlops(ml.value)
    if (r.status === 'fulfilled')  setRuns(r.value.runs || [])
    Promise.allSettled([
      axios.get('/api/mlops/drift').then(x => x.data),
      axios.get('/api/mlops/percentiles').then(x => x.data),
      axios.get('/api/mlops/throughput').then(x => x.data),
      axios.get('/api/mlops/timeseries').then(x => x.data),
      axios.get('/api/mlops/models-used').then(x => x.data),
      axios.get('/api/mlops/errors').then(x => x.data),
    ]).then(([d, p, t, s, mu, er]) => {
      if (d.status === 'fulfilled') setDrift(d.value)
      if (p.status === 'fulfilled') setPct(p.value)
      if (t.status === 'fulfilled') setTp(t.value)
      if (s.status === 'fulfilled') setSeries(s.value?.series || [])
      if (mu.status === 'fulfilled') setModelsUsed(mu.value?.models || [])
      if (er.status === 'fulfilled') setErrors(er.value || {})
    })
    setLoading(false)
  }

  const fmtMs = (ms) => !ms ? '—' : ms < 1000 ? `${Math.round(ms)}ms` : `${(ms/1000).toFixed(1)}s`
  const latColor = (ms) => !ms ? 'var(--text-3)' : ms < 5000 ? 'var(--green)' : ms < 15000 ? 'var(--amber)' : 'var(--red)'

  const seriesVals = createMemo(() => series().map(s => s.avg || 0))

  const projection = createMemo(() => {
    const tp = throughput()
    const totalRuns = mlops()?.total_runs ?? kpis()?.total_requests ?? 0
    const perDay = tp?.last_day ?? Math.round(totalRuns / 30)
    const perHour = tp?.last_hour ?? 0
    const projMonth = perDay > 0 ? perDay * 30 : totalRuns
    const costPerRunCloud = 0.0006
    const savedMonth = projMonth * costPerRunCloud
    return { perDay, perHour, projMonth, savedMonth, totalRuns }
  })

  const successSegments = createMemo(() => {
    const ok = mlops()?.finished ?? 0
    const fail = mlops()?.failed ?? 0
    if (ok + fail === 0) {
      const tot = kpis()?.total_requests ?? 0
      const sr = (kpis()?.success_rate_pct ?? kpis()?.success_rate ?? 100) / 100
      return [
        { label: 'Éxito', value: Math.round(tot * sr), color: 'var(--green)' },
        { label: 'Fallo', value: Math.round(tot * (1 - sr)), color: 'var(--red)' },
      ]
    }
    return [
      { label: 'Completados', value: ok, color: 'var(--green)' },
      { label: 'Fallidos', value: fail, color: 'var(--red)' },
    ]
  })

  return (
    <div class="panel-page">
      <div class="panel-page-header">
        <div>
          <div class="panel-page-title">{t('stat.stats')}</div>
          <div class="panel-page-sub">{t('stp.subtitle')}</div>
        </div>
        <button class="btn btn-ghost" onClick={loadAll} disabled={loading()}>{t('common.refresh')}</button>
      </div>

      <div class="tabs">
        <button class={`tab-btn ${tab()==='activity'?'active':''}`} onClick={() => setTab('activity')}>{t('stp.activity')}</button>
        <button class={`tab-btn ${tab()==='performance'?'active':''}`} onClick={() => setTab('performance')}>Rendimiento</button>
        <button class={`tab-btn ${tab()==='projections'?'active':''}`} onClick={() => setTab('projections')}>Proyecciones</button>
      </div>

      {/* ACTIVIDAD */}
      <Show when={tab()==='activity'}>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">{t('ui2.total_requests')}</div>
            <div class="kpi-val" style="color:var(--blue)">{kpis()?.total_requests ?? 0}</div>
            <Sparkline values={seriesVals()} color="var(--blue)" />
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{t('stat.success_rate')}</div>
            <div class="kpi-val" style="color:var(--green)">{(kpis()?.success_rate_pct ?? kpis()?.success_rate ?? 100).toFixed(0)}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{t('stat.degradation')}</div>
            <div class="kpi-val" style="color:var(--amber);font-size:22px">{(kpis()?.degradation_rate ?? 0).toFixed(0)}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">TTFT medio</div>
            <div class="kpi-val" style={`color:${latColor(kpis()?.avg_ttft_ms)};font-size:22px`}>{fmtMs(kpis()?.avg_ttft_ms)}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">{t('ui2.latency_trend')}</div>
          <LineChart values={seriesVals()} height={180}
            empty="Necesitas al menos 2 ejecuciones para ver la tendencia. Haz varias preguntas en el Chat." />
          <Show when={seriesVals().length > 1}>
            <div style="font-size:11px;color:var(--text-3);text-align:center;margin-top:6px">{t('stat.oldest_newest')}</div>
          </Show>
        </div>

        <div class="card">
          <div class="card-title">{t('ui2.recent_activity')}</div>
          <Show when={traces().length > 0} fallback={
            <div style="text-align:center;padding:40px;color:var(--text-3);font-size:13px">{t('ui2.no_activity')}</div>
          }>
            <table class="g-table">
              <thead><tr><th>Prompt</th><th>Estrategia</th><th>Especialistas</th><th>Latencia</th><th></th></tr></thead>
              <tbody>
                <For each={traces()}>
                  {(t) => (
                    <tr>
                      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{t.prompt_preview || '—'}</td>
                      <td style="font-family:var(--mono);font-size:11px;color:var(--text-3)">{t.strategy_effective || '—'}</td>
                      <td style="font-size:11px;color:var(--text-3)">{(t.specialists_used||[]).join(', ') || '—'}</td>
                      <td style={`font-family:var(--mono);font-size:11px;color:${latColor(t.latency_ms)}`}>{fmtMs(t.latency_ms)}</td>
                      <td><span style={`color:${t.success?'var(--green)':'var(--red)'};font-weight:700`}>{t.success?'OK':'ERR'}</span></td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </Show>
        </div>
      </Show>

      {/* RENDIMIENTO */}
      <Show when={tab()==='performance'}>
        <div class="chart-grid-2">
          <div class="card">
            <div class="card-title">{t('stat.success_rate')}</div>
            <div style="display:flex;justify-content:center;padding:8px 0">
              <GaugeRing value={kpis()?.success_rate_pct ?? kpis()?.success_rate ?? 100} max={100} sublabel={t('kpi.success')} />
            </div>
          </div>
          <div class="card">
            <div class="card-title">{t('ui2.exec_split')}</div>
            <div style="padding:8px 0"><Donut segments={successSegments()} /></div>
          </div>
        </div>

        <Show when={pct() && pct().count > 0}>
          <div class="card">
            <div class="card-title">Percentiles de latencia · {pct().count} muestras</div>
            <div class="kpi-grid" style="margin-bottom:0">
              <div class="kpi-card"><div class="kpi-label">P50</div><div class="kpi-val" style={`font-size:18px;color:${latColor(pct().p50)}`}>{fmtMs(pct().p50)}</div></div>
              <div class="kpi-card"><div class="kpi-label">P90</div><div class="kpi-val" style={`font-size:18px;color:${latColor(pct().p90)}`}>{fmtMs(pct().p90)}</div></div>
              <div class="kpi-card"><div class="kpi-label">P95</div><div class="kpi-val" style={`font-size:18px;color:${latColor(pct().p95)}`}>{fmtMs(pct().p95)}</div></div>
              <div class="kpi-card"><div class="kpi-label">P99</div><div class="kpi-val" style={`font-size:18px;color:${latColor(pct().p99)}`}>{fmtMs(pct().p99)}</div></div>
              <div class="kpi-card"><div class="kpi-label">Min</div><div class="kpi-val" style="font-size:18px;color:var(--green)">{fmtMs(pct().min)}</div></div>
              <div class="kpi-card"><div class="kpi-label">Max</div><div class="kpi-val" style="font-size:18px;color:var(--red)">{fmtMs(pct().max)}</div></div>
            </div>
          </div>
        </Show>

        <Show when={drift()}>
          <div class="card" style={`border-color:${drift().drift_detected ? 'rgba(248,113,113,0.3)' : 'var(--glass-border)'}`}>
            <div class="card-title">{t('stat.drift')}</div>
            <Show when={drift().baseline > 0} fallback={
              <div style="font-size:13px;color:var(--text-3)">{drift().reason || 'Sin datos suficientes'}</div>
            }>
              <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
                <div style={`font-size:13px;font-weight:700;padding:6px 14px;border-radius:10px;background:${drift().drift_detected?'rgba(248,113,113,0.15)':'rgba(52,211,153,0.15)'};color:${drift().drift_detected?'var(--red)':'var(--green)'}`}>
                  {drift().drift_detected ? 'DRIFT DETECTADO' : 'Estable'}
                </div>
                <div style="font-size:13px;color:var(--text-2)">
                  Baseline: <b>{fmtMs(drift().baseline)}</b> → Reciente: <b>{fmtMs(drift().recent)}</b>
                  <span style={`margin-left:8px;color:${drift().change_pct>0?'var(--red)':'var(--green)'}`}>
                    ({drift().change_pct > 0 ? '+' : ''}{drift().change_pct}%)
                  </span>
                </div>
              </div>
            </Show>
          </div>
        </Show>

        <Show when={modelsUsed().length > 0}>
          <div class="chart-grid-2">
            <div class="card">
              <div class="card-title">{t('ui2.use_by_model')}</div>
              <BarSeries items={[...modelsUsed()]
                .sort((a,b)=>((b.success_count||0)+(b.error_count||0))-((a.success_count||0)+(a.error_count||0)))
                .slice(0,8)
                .map(m => ({ label: m.model_name, value: (m.success_count||0)+(m.error_count||0), display: (m.success_count||0)+(m.error_count||0) }))} />
            </div>
            <div class="card">
              <div class="card-title">{t('ui2.latency_by_model')}</div>
              <BarSeries items={[...modelsUsed()]
                .sort((a,b)=>(b.avg_latency_ms||0)-(a.avg_latency_ms||0))
                .slice(0,8)
                .map(m => ({ label: m.model_name, value: m.avg_latency_ms||0, display: fmtMs(m.avg_latency_ms), color: latColor(m.avg_latency_ms) }))} />
            </div>
          </div>
        </Show>

        <Show when={mlops()?.strategy_distribution && Object.keys(mlops().strategy_distribution).length > 0}>
          <div class="card">
            <div class="card-title">{t('stat.strategy_dist')}</div>
            <BarSeries items={Object.entries(mlops().strategy_distribution)
              .sort((a,b)=>b[1]-a[1])
              .map(([s,c]) => ({ label: s, value: c, display: String(c) }))} />
          </div>
        </Show>

        <Show when={mlops()?.model_registry && mlops().model_registry.length > 0}>
          <div class="card">
            <div class="card-title">{t('stat.model_registry')}</div>
            <table class="g-table">
              <thead><tr><th>Especialista</th><th>Modelo</th><th>Tier</th><th>Latencia</th><th>{t('stat.successes')}</th><th>{t('common.errors')}</th></tr></thead>
              <tbody>
                <For each={mlops().model_registry}>
                  {(m) => (
                    <tr>
                      <td style="font-size:12px">{m.specialist_id}</td>
                      <td style="font-family:var(--mono);font-size:11px;color:var(--text-3)">{m.model_name}</td>
                      <td>T{m.hardware_tier}</td>
                      <td style={`font-family:var(--mono);font-size:11px;color:${latColor(m.avg_latency_ms)}`}>{fmtMs(m.avg_latency_ms)}</td>
                      <td style="color:var(--green)">{m.success_count || 0}</td>
                      <td style={`color:${(m.error_count||0)>0?'var(--red)':'var(--text-3)'}`}>{m.error_count || 0}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </div>
        </Show>

        <div class="card">
          <div class="card-title">{t('stat.export')}</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <a href="/api/mlops/export/csv" target="_blank" class="btn btn-glass" style="text-decoration:none">CSV</a>
            <a href="/api/mlops/export/prometheus" target="_blank" class="btn btn-glass" style="text-decoration:none">Prometheus</a>
          </div>
          <div style="font-size:12px;color:var(--text-3);margin-top:10px">{t('stat.export_note')}</div>
        </div>
      </Show>

      {/* PROYECCIONES */}
      <Show when={tab()==='projections'}>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">Runs / hora</div>
            <div class="kpi-val" style="color:var(--teal)">{projection().perHour}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{t('stat.runs_day')}</div>
            <div class="kpi-val" style="color:var(--blue)">{projection().perDay}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{t('stat.projection30')}</div>
            <div class="kpi-val" style="color:var(--purple)">{projection().projMonth.toLocaleString()}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">{t('ui2.total_accum')}</div>
            <div class="kpi-val" style="color:var(--green)">{projection().totalRuns.toLocaleString()}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">{t('ui2.cost_avoided')}</div>
          <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;padding:6px 0">
            <div>
              <div style="font-size:34px;font-weight:800;background:var(--grad-primary);-webkit-background-clip:text;background-clip:text;color:transparent">
                ${projection().savedMonth.toFixed(2)}
              </div>
              <div style="font-size:12px;color:var(--text-3)">estimado / mes ejecutando local</div>
            </div>
            <div style="flex:1;min-width:200px">
              <div style="font-size:13px;color:var(--text-2);line-height:1.6">
                Con tu ritmo actual proyectado a 30 días, una API cloud equivalente
                facturaría alrededor de <b style="color:var(--text-1)">${projection().savedMonth.toFixed(2)}</b>.
                En Andromeda esa inferencia corre en tu hardware: coste de API <b style="color:var(--green)">$0</b>.
              </div>
            </div>
          </div>
          <div class="proj-note">
            Estimación ilustrativa: ~1.5k tokens de salida por run a precio de referencia de un modelo cloud económico.
            El ahorro real depende del modelo comparado y del tamaño de tus prompts.
          </div>
        </div>

        <div class="card">
          <div class="card-title">{t('ui2.throughput_total')}</div>
          <LineChart values={seriesVals()} height={160}
            empty="Sin suficientes ejecuciones para proyectar. Usa el Chat unas cuantas veces." />
        </div>

        <Show when={errors() && (errors().by_strategy?.length > 0)}>
          <div class="card">
            <div class="card-title">{t('ui2.fails_strategy')}</div>
            <div style="display:flex;flex-direction:column;gap:8px;margin-top:4px">
              <For each={errors().by_strategy}>
                {(e) => (
                  <div style="display:flex;align-items:center;justify-content:space-between;font-size:12px">
                    <span style="color:var(--text-2);font-family:var(--mono)">{e.strategy || '—'}</span>
                    <span style={`font-weight:700;color:${(e.failed||0)>0?'var(--red)':'var(--green)'}`}>{e.failed || 0} / {e.total || 0}</span>
                  </div>
                )}
              </For>
            </div>
          </div>
        </Show>
      </Show>
    </div>
  )
}
