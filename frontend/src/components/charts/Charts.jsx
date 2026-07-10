/**
 * Charts.jsx — Gráficos SVG ligeros, sin dependencias, estética "Apple".
 *
 * Principios de diseño:
 *   - Gradientes suaves multi-stop, nunca colores planos
 *   - Animaciones de entrada con easing tipo spring (draw-in, grow, sweep)
 *   - Tipografía grande y fina, mucho aire
 *   - Esquinas redondeadas, glow sutil en puntos de interés
 *   - Todo lee colores del tema vía variables CSS (claro/oscuro automático)
 *
 * Mismas firmas públicas que la versión anterior (no rompe consumidores):
 *   <LineChart values avg /> · <Sparkline values color /> ·
 *   <BarSeries items /> · <Donut segments /> · <GaugeRing value max />
 */
import { For, Show, createMemo, onMount, createSignal } from 'solid-js'

const PAD = 8

// Catmull-Rom -> Bezier: curva suave que pasa por todos los puntos.
function smoothPath(pts) {
  if (pts.length < 2) return ''
  let d = `M ${pts[0][0]},${pts[0][1]}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] || p2
    const c1x = p1[0] + (p2[0] - p0[0]) / 6
    const c1y = p1[1] + (p2[1] - p0[1]) / 6
    const c2x = p2[0] - (p3[0] - p1[0]) / 6
    const c2y = p2[1] - (p3[1] - p1[1]) / 6
    d += ` C ${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`
  }
  return d
}

// Hook: dispara una animacion de entrada al montar.
function useEnter(delay = 0) {
  const [on, setOn] = createSignal(false)
  onMount(() => setTimeout(() => setOn(true), delay))
  return on
}

export function LineChart(props) {
  const W = props.width || 640
  const H = props.height || 180
  const data = () => props.values || []
  const id = `lg-${Math.random().toString(36).slice(2, 8)}`
  const entered = useEnter(60)

  const geom = createMemo(() => {
    const vs = data()
    if (vs.length < 2) return null
    const max = Math.max(...vs, 1)
    const min = Math.min(...vs, 0)
    const range = max - min || 1
    const innerW = W - PAD * 2
    const innerH = H - PAD * 2
    const pts = vs.map((v, i) => [
      PAD + (i / (vs.length - 1)) * innerW,
      PAD + innerH - ((v - min) / range) * innerH,
    ])
    const line = smoothPath(pts)
    const area = `${line} L ${pts[pts.length - 1][0]},${H - PAD} L ${pts[0][0]},${H - PAD} Z`
    const len = pts.reduce((acc, p, i) => i === 0 ? 0 : acc + Math.hypot(p[0] - pts[i-1][0], p[1] - pts[i-1][1]), 0)
    return { pts, line, area, max, min, len: Math.ceil(len) + 40 }
  })

  return (
    <Show when={geom()} fallback={<EmptyChart h={H} label={props.empty || 'Sin datos suficientes'} />}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={`width:100%;height:${H}px;display:block;overflow:visible`}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--blue)" stop-opacity="0.28" />
            <stop offset="55%" stop-color="var(--blue)" stop-opacity="0.08" />
            <stop offset="100%" stop-color="var(--blue)" stop-opacity="0" />
          </linearGradient>
          <linearGradient id={`${id}-stroke`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#c87bd8" />
            <stop offset="100%" stop-color="var(--blue)" />
          </linearGradient>
          <filter id={`${id}-glow`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <For each={[0.25, 0.5, 0.75]}>
          {(f) => <line x1={PAD} y1={PAD + f * (H - PAD * 2)} x2={W - PAD} y2={PAD + f * (H - PAD * 2)}
            stroke="var(--hairline)" stroke-width="1" />}
        </For>
        <path d={geom().area} fill={`url(#${id})`}
          style={`opacity:${entered() ? 1 : 0};transition:opacity .8s ease .2s`} />
        <path d={geom().line} fill="none" stroke={`url(#${id}-stroke)`} stroke-width="3"
          stroke-linecap="round" stroke-linejoin="round"
          stroke-dasharray={geom().len}
          stroke-dashoffset={entered() ? 0 : geom().len}
          style="transition:stroke-dashoffset 1.1s cubic-bezier(0.4,0,0.2,1)" />
        <For each={geom().pts}>
          {(p, i) => (
            <Show when={i() === geom().pts.length - 1}>
              <circle cx={p[0]} cy={p[1]} r="4.5" fill="var(--blue)" filter={`url(#${id}-glow)`}
                style={`opacity:${entered() ? 1 : 0};transition:opacity .5s ease 1s`} />
            </Show>
          )}
        </For>
      </svg>
    </Show>
  )
}

export function Sparkline(props) {
  const W = 120, H = 34
  const data = () => props.values || []
  const path = createMemo(() => {
    const vs = data()
    if (vs.length < 2) return null
    const max = Math.max(...vs, 1), min = Math.min(...vs, 0)
    const range = max - min || 1
    const pts = vs.map((v, i) => [
      (i / (vs.length - 1)) * W,
      H - 3 - ((v - min) / range) * (H - 6),
    ])
    return smoothPath(pts)
  })
  return (
    <Show when={path()}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style="width:100%;height:34px;display:block">
        <path d={path()} fill="none" stroke={props.color || 'var(--blue)'} stroke-width="2.2"
          stroke-linecap="round" stroke-linejoin="round" opacity="0.9" />
      </svg>
    </Show>
  )
}

export function BarSeries(props) {
  const items = () => props.items || []
  const max = createMemo(() => Math.max(...items().map(i => i.value || 0), 1))
  const entered = useEnter(80)
  return (
    <div style="display:flex;flex-direction:column;gap:11px">
      <For each={items()}>
        {(it, idx) => {
          const pct = () => Math.max(2, Math.round((it.value || 0) * 100 / max()))
          return (
            <div style="display:flex;align-items:center;gap:12px">
              <div style="width:130px;font-family:var(--mono);font-size:11px;color:var(--text-2);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title={it.label}>{it.label}</div>
              <div class="chart-bar-track" style="border-radius:99px;overflow:hidden">
                <div class="chart-bar-fill" style={`width:${entered() ? pct() : 0}%;background:${it.color || 'var(--grad-primary)'};border-radius:99px;transition:width .9s cubic-bezier(0.34,1.3,0.5,1) ${idx() * 70}ms`}>
                  <span class="chart-bar-val">{it.display ?? it.value}</span>
                </div>
              </div>
            </div>
          )
        }}
      </For>
    </div>
  )
}

export function Donut(props) {
  const segs = () => (props.segments || []).filter(s => s.value > 0)
  const total = createMemo(() => segs().reduce((a, s) => a + s.value, 0) || 1)
  const R = 52, C = 60, SW = 14
  const circ = 2 * Math.PI * R
  const entered = useEnter(100)
  return (
    <div style="display:flex;align-items:center;gap:26px;flex-wrap:wrap">
      <svg viewBox="0 0 120 120" style="width:128px;height:128px;flex-shrink:0;transform:rotate(-90deg)">
        <circle cx={C} cy={C} r={R} fill="none" stroke="var(--hairline)" stroke-width={SW} />
        {(() => {
          let acc = 0
          return (
            <For each={segs()}>
              {(s) => {
                const frac = s.value / total()
                const dash = frac * circ
                const offset = -acc * circ
                acc += frac
                return (
                  <circle cx={C} cy={C} r={R} fill="none" stroke={s.color} stroke-width={SW}
                    stroke-dasharray={`${entered() ? dash : 0} ${circ - (entered() ? dash : 0)}`}
                    stroke-dashoffset={offset}
                    stroke-linecap="round"
                    style="transition:stroke-dasharray .9s cubic-bezier(0.34,1.2,0.5,1)" />
                )
              }}
            </For>
          )
        })()}
      </svg>
      <div style="display:flex;flex-direction:column;gap:9px">
        <For each={segs()}>
          {(s) => (
            <div style="display:flex;align-items:center;gap:9px;font-size:12.5px">
              <span style={`width:10px;height:10px;border-radius:3px;background:${s.color};flex-shrink:0`} />
              <span style="color:var(--text-2)">{s.label}</span>
              <span style="color:var(--text-1);font-weight:700;margin-left:auto;font-family:var(--mono)">{Math.round(s.value / total() * 100)}%</span>
            </div>
          )}
        </For>
      </div>
    </div>
  )
}

export function GaugeRing(props) {
  const noData = () => props.value == null
  const v = () => Math.max(0, Math.min(props.value ?? 0, props.max ?? 100))
  const frac = () => noData() ? 0 : v() / (props.max ?? 100)
  const R = 50, C = 60, SW = 12
  const circ = 2 * Math.PI * R
  const entered = useEnter(120)
  const color = () => noData() ? 'var(--text-3)' : (props.color || (frac() >= 0.9 ? 'var(--green)' : frac() >= 0.6 ? 'var(--amber)' : 'var(--red)'))
  const gid = `gg-${Math.random().toString(36).slice(2, 7)}`
  return (
    <div style="position:relative;width:124px;height:124px">
      <svg viewBox="0 0 120 120" style="width:124px;height:124px;transform:rotate(-90deg)">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color={color()} stop-opacity="0.7" />
            <stop offset="100%" stop-color={color()} />
          </linearGradient>
        </defs>
        <circle cx={C} cy={C} r={R} fill="none" stroke="var(--hairline)" stroke-width={SW} />
        <circle cx={C} cy={C} r={R} fill="none" stroke={`url(#${gid})`} stroke-width={SW}
          stroke-dasharray={`${(entered() ? frac() : 0) * circ} ${circ}`} stroke-linecap="round"
          style="transition:stroke-dasharray 1s cubic-bezier(0.34,1.4,0.5,1)" />
      </svg>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
        <span style={`font-size:28px;font-weight:700;letter-spacing:-0.02em;color:${color()}`}>{noData() ? '—' : Math.round(frac() * 100) + '%'}</span>
        <Show when={props.sublabel}><span style="font-size:10px;color:var(--text-3)">{props.sublabel}</span></Show>
      </div>
    </div>
  )
}

function EmptyChart(props) {
  return (
    <div style={`height:${props.h}px;display:flex;align-items:center;justify-content:center;color:var(--text-3);font-size:12.5px;text-align:center;line-height:1.5`}>
      {props.label}
    </div>
  )
}
