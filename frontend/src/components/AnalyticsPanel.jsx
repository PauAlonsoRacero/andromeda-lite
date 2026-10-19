/**
 * AnalyticsPanel.jsx — Observabilidad de Andromeda Lite.
 *
 * Hace visible todo lo que el backend ya mide:
 *   - Memoria: total, categorías, tamaño medio, hit rate de búsqueda
 *   - Herramientas MCP: uso por herramienta, latencia, error rate
 *   - Rendimiento: latencias p50/p95/p99, success rate
 *   - Errores recientes
 *
 * Datos desde /api/traces/metrics (realtime + tools) y /api/memory/stats.
 * Charts SVG nativos reutilizados de ./charts/Charts.jsx (sin dependencias).
 */
import { createSignal, onMount, onCleanup, For, Show, createMemo } from 'solid-js'
import ComponentsHealth from './ComponentsHealth.jsx'
import axios from 'axios'
import { on, SYSTEM_CHANGED } from '../stores/events.js'
import { BarSeries, Donut, GaugeRing, LineChart } from './charts/Charts.jsx'
import InfoButton from './InfoButton.jsx'
import { t } from '../stores/i18n.js'

const CAT_COLORS = ['#5b9cf6', '#34d399', '#a78bfa', '#fbbf24', '#f472b6', '#94a3b8']

export default function AnalyticsPanel() {
  const [rt, setRt]         = createSignal(null)   // realtime metrics
  const [tools, setTools]   = createSignal(null)   // tool analytics
  const [mem, setMem]       = createSignal(null)   // memory stats
  // Solo la PRIMERA carga muestra el estado de carga. Los refrescos periódicos
  // actualizan los valores en su sitio: si se desmonta el árbol cada 5 s, la
  // vista salta y hace imposible leer nada.
  const [firstLoad, setFirstLoad] = createSignal(true)
  const [err, setErr]       = createSignal(false)
  let timer

  onMount(() => { loadAll(); timer = setInterval(loadAll, 5000) })
  onCleanup(() => timer && clearInterval(timer))
  // Refresco inmediato cuando cambia algo del sistema, sin esperar al sondeo.
  onCleanup(on(SYSTEM_CHANGED, () => loadAll()))

  async function loadAll() {
    try {
      const [m, mem2] = await Promise.allSettled([
        axios.get('/api/traces/metrics').then(x => x.data),
        axios.get('/api/memory/stats').then(x => x.data),
      ])
      if (m.status === 'fulfilled') {
        setRt(m.value?.realtime || {})
        setTools(m.value?.tools || { total_calls: 0, by_tool: {} })
      }
      if (mem2.status === 'fulfilled') setMem(mem2.value || {})
      setErr(false)
    } catch {
      setErr(true)
    } finally {
      setFirstLoad(false)
    }
  }

  const fmtMs = (ms) => ms == null ? '—' : ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
  const pct = (v) => v == null ? '—' : `${Math.round(v * 100)}%`

  // ── Derivados ──────────────────────────────────────────────────────────
  const memCategories = createMemo(() => {
    const by = mem()?.by_category || {}
    return Object.entries(by).map(([label, value], i) => ({
      label, value, color: CAT_COLORS[i % CAT_COLORS.length],
    }))
  })

  const toolBars = createMemo(() => {
    const by = tools()?.by_tool || {}
    return Object.entries(by).map(([name, d], i) => ({
      label: name,
      value: d.calls,
      display: `${d.calls}  ·  ${fmtMs(d.avg_latency_ms)}  ·  ${pct(d.error_rate)} ${t('an.err')}`,
      color: d.error_rate > 0 ? 'var(--amber, #fbbf24)' : 'var(--grad-primary)',
    }))
  })

  const recentTools = createMemo(() => (tools()?.recent || []).slice().reverse())

  return (
    <div style="max-width:920px;margin:0 auto;padding:26px 22px 60px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <div style="display:flex;align-items:center;gap:10px">
          <h2 style="font-size:21px;font-weight:800;color:var(--text-1);margin:0">{t('an.title')}</h2>
          <InfoButton title={t('an.title')} intro={t('info.an.intro')} tip={t('info.an.tip')} items={[
            { h: t('info.an.1h'), d: t('info.an.1d') },
            { h: t('info.an.2h'), d: t('info.an.2d') },
            { h: t('info.an.3h'), d: t('info.an.3d') },
            { h: t('info.an.4h'), d: t('info.an.4d') },
            { h: t('info.an.5h'), d: t('info.an.5d') },
          ]} />
        </div>
        <span style="font-size:var(--fs-xs);color:var(--text-3);font-family:var(--mono)">
          {t('an.refresh')}
        </span>
      </div>
      <p style="color:var(--text-2);font-size:var(--fs-base);margin:0 0 22px">
        {t('an.subtitle')}
      </p>

      <Show when={!firstLoad()} fallback={
        <div style="display:flex;flex-direction:column;gap:10px;padding:8px 0">
          <For each={Array(4)}>{() => <div class="skeleton" style="height:76px;border-radius:14px" />}</For>
        </div>
      }>

        {/* ── KPIs principales ───────────────────────────────────────── */}
        <div style="display:grid;grid-template-columns:auto 1fr;gap:18px;align-items:center;margin-bottom:26px;background:var(--surface-1,rgba(255,255,255,.02));border:1px solid var(--hairline,rgba(255,255,255,.07));border-radius:20px;padding:22px 24px">
          <div style="display:flex;flex-direction:column;align-items:center;gap:6px">
            <GaugeRing value={(rt()?.total_requests ?? 0) > 0 ? (rt()?.success_rate_pct ?? null) : null} max={100} sublabel={t("an.success")} />
          </div>
          <div class="stagger" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px">
            <Kpi label={t("an.requests")} value={rt()?.total_requests ?? 0} sub={`${rt()?.requests_last_hour ?? 0} · ${t('an.req_hour')}`} />
            <Kpi label={t("an.lat_p50")} value={fmtMs(rt()?.p50_latency_ms)}
                 info={{ title: t('info.pct.title'), intro: t('info.pct.intro'), items: [
                   { h: t('info.pct.p50h'), d: t('info.pct.p50d') },
                   { h: t('info.pct.p95h'), d: t('info.pct.p95d') },
                   { h: t('info.pct.p99h'), d: t('info.pct.p99d') },
                   { h: t('info.pct.whyh'), d: t('info.pct.whyd') },
                 ] }} />
            <Kpi label={t("an.lat_p95")} value={fmtMs(rt()?.p95_latency_ms)}
                 info={{ title: t('info.pct.title'), intro: t('info.pct.intro'), items: [
                   { h: t('info.pct.p50h'), d: t('info.pct.p50d') },
                   { h: t('info.pct.p95h'), d: t('info.pct.p95d') },
                   { h: t('info.pct.p99h'), d: t('info.pct.p99d') },
                   { h: t('info.pct.whyh'), d: t('info.pct.whyd') },
                 ] }} />
            <Kpi label={t("an.ttft")} value={fmtMs(rt()?.avg_ttft_ms)} />
          </div>
        </div>

        {/* ── Perfil de latencia ─────────────────────────────────────── */}
        <Show when={(rt()?.total_requests ?? 0) > 0}>
          <Section title={t("an.perf")}>
            <div style="font-size:var(--fs-sm);color:var(--text-3);margin-bottom:10px">{t('an.lat_profile')}</div>
            <BarSeries items={[
              { label: 'p50', value: rt()?.p50_latency_ms ?? 0, display: fmtMs(rt()?.p50_latency_ms), color: 'var(--green)' },
              { label: 'p95', value: rt()?.p95_latency_ms ?? 0, display: fmtMs(rt()?.p95_latency_ms), color: 'var(--blue)' },
              { label: 'p99', value: rt()?.p99_latency_ms ?? 0, display: fmtMs(rt()?.p99_latency_ms), color: 'var(--purple)' },
              { label: t('an.avg'), value: rt()?.avg_latency_ms ?? 0, display: fmtMs(rt()?.avg_latency_ms), color: 'var(--amber,#f0a35f)' },
            ]} />
          </Section>
        </Show>

        {/* ── Memoria ────────────────────────────────────────────────── */}
        <Section title={t("an.memory")}>
          <div class="stagger" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px">
            <Kpi label={t("an.memories")} value={mem()?.total ?? 0} small />
            <Kpi label={t("an.avg_size")} value={mem()?.avg_content_chars ? `${Math.round(mem().avg_content_chars)} ${t('an.chars')}` : '—'} small />
            <Kpi label={t("an.hit_rate")} value={pct(mem()?.search_hit_rate)} small
                 sub={`${mem()?.search_count ?? 0} ${t('an.searches')}`} />
            <Kpi label={t("an.db_disk")} value={mem()?.db_size_kb ? `${mem().db_size_kb} KB` : '—'} small />
          </div>
          <Show when={memCategories().length > 0}
                fallback={<Empty text={t("an.mem_empty")} />}>
            <div style="font-size:var(--fs-sm);color:var(--text-3);margin-bottom:8px">{t('an.by_category')}</div>
            <Donut segments={memCategories()} />
          </Show>
        </Section>

        {/* ── Herramientas MCP ───────────────────────────────────────── */}
        <Section title={t("an.tools")}>
          <Show when={(tools()?.total_calls ?? 0) > 0}
                fallback={<Empty text={t("an.tools_empty")} />}>
            <div style="font-size:var(--fs-sm);color:var(--text-3);margin-bottom:10px">
              {tools().total_calls} {t('an.tools_legend')}
            </div>
            <BarSeries items={toolBars()} />

            <div style="font-size:var(--fs-sm);color:var(--text-3);margin:20px 0 8px">{t('an.recent')}</div>
            <div style="display:flex;flex-direction:column;gap:6px">
              <For each={recentTools()}>
                {(t) => (
                  <div style="display:flex;align-items:center;gap:10px;font-size:var(--fs-sm);font-family:var(--mono);padding:7px 10px;background:var(--surface-2,rgba(255,255,255,.03));border-radius:10px">
                    <span style={`width:7px;height:7px;border-radius:50%;flex-shrink:0;background:${t.success ? 'var(--green,#34d399)' : 'var(--red,#f87171)'}`} />
                    <span style="color:var(--text-1);font-weight:600">{t.tool}</span>
                    <span style="color:var(--text-3)">{fmtMs(t.latency_ms)}</span>
                    <Show when={t.error}>
                      <span style="color:var(--red,#f87171);margin-left:auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px" title={t.error}>{t.error}</span>
                    </Show>
                  </div>
                )}
              </For>
            </div>
          </Show>
        </Section>

      </Show>

      {/* Monitorización de calidad en el tiempo: SLO + drift */}
      <QualitySLO />

      {/* Estado de los componentes: al final, porque responde a "¿por qué no
          funciona algo?", una pregunta que surge tras mirar las métricas. */}
      <div style="height:var(--sp-6)" />
      <ComponentsHealth />
    </div>
  )
}

// ── Subcomponentes ─────────────────────────────────────────────────────────

function Kpi(props) {
  return (
    <div style="background:var(--surface-2,rgba(255,255,255,.03));border:1px solid var(--hairline,rgba(255,255,255,.07));border-radius:14px;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:5px;margin-bottom:7px">
        <span style="font-size:var(--fs-micro);color:var(--text-3);text-transform:uppercase;letter-spacing:.05em">{props.label}</span>
        <Show when={props.info}>
          <InfoButton title={props.info.title} intro={props.info.intro} items={props.info.items} />
        </Show>
      </div>
      <div style={`font-size:${props.small ? '20px' : '26px'};font-weight:700;letter-spacing:-0.02em;font-variant-numeric:tabular-nums;color:${props.color || 'var(--text-1)'}`}>{props.value}</div>
      <Show when={props.sub}>
        <div style="font-size:var(--fs-micro);color:var(--text-3);margin-top:3px">{props.sub}</div>
      </Show>
    </div>
  )
}

function Section(props) {
  return (
    <div style="background:var(--surface-1,rgba(255,255,255,.02));border:1px solid var(--hairline,rgba(255,255,255,.07));border-radius:14px;padding:20px 22px;margin-bottom:18px">
      <h3 style="font-size:var(--fs-md);font-weight:700;color:var(--text-1);margin:0 0 16px">{props.title}</h3>
      {props.children}
    </div>
  )
}

function Empty(props) {
  return <div style="color:var(--text-3);font-size:var(--fs-base);padding:18px 0;text-align:center">{props.text}</div>
}

// ── Monitorización de calidad: SLO + drift en el tiempo ─────────────────────
const DIR_ICON = { improving: '▲', degrading: '▼', stable: '–' }
const DIR_COLOR = { improving: 'var(--green)', degrading: 'var(--red)', stable: 'var(--text-3)' }

function QualitySLO() {
  const [data, setData] = createSignal(null)

  async function load() {
    try {
      const r = await axios.get('/api/traces/quality/history')
      setData(r.data)
    } catch { /* noop */ }
  }
  onMount(() => {
    load()
    const id = setInterval(load, 30_000)
    onCleanup(() => clearInterval(id))
  })

  const points = () => data()?.points || []
  const asmt = () => data()?.assessment || {}
  const status = () => asmt().status || {}
  const trend = () => asmt().trend || {}

  return (
    <Show when={points().length > 0 && !asmt().insufficient} fallback={
      <Section title={t('slo.title')}>
        <Empty text={asmt().insufficient
          ? t('slo.insufficient').replace('{n}', asmt().requests ?? 0).replace('{min}', asmt().min_requests ?? 20)
          : t('slo.empty')} />
      </Section>
    }>
      <Section title={t('slo.title')}>
        {/* Tarjetas de estado SLO */}
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px">
          <SloCard label={t('slo.success')} s={status().success_rate} unit="%" tr={trend().success_rate} />
          <SloCard label={t('slo.p95')} s={status().p95_latency} unit="ms" tr={trend().p95} invert />
          <SloCard label={t('slo.satisfaction')} s={status().satisfaction} unit="%" tr={trend().satisfaction} />
        </div>

        {/* Gráficas de tendencia */}
        <div style="font-size:var(--fs-xs);color:var(--text-3);margin-bottom:6px">{t('slo.satisfaction')} · {t('slo.over_time')}</div>
        <LineChart values={points().map(p => p.satisfaction).filter(v => v != null)} height={120} empty={t('slo.empty')} />
        <div style="font-size:var(--fs-xs);color:var(--text-3);margin:14px 0 6px">{t('slo.p95')} · {t('slo.over_time')}</div>
        <LineChart values={points().map(p => p.p95).filter(v => v != null)} height={120} empty={t('slo.empty')} />

        <Show when={asmt().breaching}>
          <div style="margin-top:14px;padding:10px 12px;border-radius:10px;background:color-mix(in srgb, var(--red) 12%, transparent);border:1px solid color-mix(in srgb, var(--red) 30%, transparent);font-size:var(--fs-sm);color:var(--red)">
            ⚠ {t('slo.breach_warn')}
          </div>
        </Show>
      </Section>
    </Show>
  )
}

function SloCard(props) {
  const ok = () => props.s?.ok
  const val = () => props.s?.value
  const color = () => ok() === false ? 'var(--red)' : ok() === true ? 'var(--green)' : 'var(--text-3)'
  return (
    <div style="background:var(--surface-2,rgba(255,255,255,.03));border:1px solid var(--hairline,rgba(255,255,255,.07));border-radius:14px;padding:14px 16px">
      <div style="font-size:var(--fs-micro);color:var(--text-3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:7px">{props.label}</div>
      <div style={`font-size:var(--fs-xl);font-weight:700;font-variant-numeric:tabular-nums;color:${color()}`}>
        {val() == null ? '—'
          /* Las latencias grandes en milisegundos son ilegibles: "107683ms" no
             se lee de un vistazo, "107.7s" sí. */
          : props.unit === 'ms' && val() >= 1000 ? `${(val() / 1000).toFixed(1)}s`
          : Math.round(val()) + props.unit}
      </div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:5px">
        <span style={`font-size:var(--fs-xs);font-weight:600;color:${color()}`}>
          {ok() === false ? t('slo.breach') : ok() === true ? t('slo.ok') : '—'}
        </span>
        <Show when={props.tr}>
          <span style={`font-size:var(--fs-xs);color:${DIR_COLOR[props.tr.direction]}`}>
            {/* Las métricas que ya son porcentaje se comparan en PUNTOS
                porcentuales ("pp"): "+33 pp" es legible, "+510 %" era absurdo. */}
            {DIR_ICON[props.tr.direction]} {Math.abs(props.tr.change_pct)}{props.tr.unit === 'pp' ? ' pp' : '%'}
          </span>
        </Show>

      </div>
    </div>
  )
}
