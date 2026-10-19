/**
 * DiagnosticsPanel.jsx — Consola de diagnóstico.
 *
 * Muestra qué hace Andromeda por dentro en cada mensaje: qué prompt recibió el
 * modelo, si buscó en internet y por qué, qué devolvió cada motor, qué
 * recuerdos recuperó y cuánto tardó cada paso.
 *
 * Existe porque diagnosticar un fallo a base de conjeturas cuesta varios
 * intentos; con el registro delante se ve directamente.
 *
 * Apagado por defecto: cuando está activo registra los prompts y respuestas
 * completos, y eso solo debe ocurrir si el usuario lo pide.
 */
import { createSignal, For, Show, onCleanup, onMount } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

const COLOR = {
  success: 'var(--green)',
  warn: 'var(--amber)',
  error: 'var(--red)',
  info: 'var(--text-3)',
}

const ICONO = {
  chat: '💬', prompt: '📝', search: '🌐', memory: '💭', rag: '📚',
  skills: '⚡', mcp: '🔌', ollama: '🧠', system: '⚙️',
}

export default function DiagnosticsPanel() {
  const [activo, setActivo] = createSignal(false)
  const [eventos, setEventos] = createSignal([])
  const [ultimoSeq, setUltimoSeq] = createSignal(0)
  const [filtro, setFiltro] = createSignal('')
  const [abierto, setAbierto] = createSignal(null)
  const [foto, setFoto] = createSignal(null)
  const [aviso, setAviso] = createSignal('')
  let timer

  onMount(async () => {
    try {
      const r = await axios.get('/api/diagnostics')
      setActivo(r.data.enabled)
      if (r.data.enabled) arrancarSondeo()
    } catch { /* el panel no es crítico: si falla, se muestra apagado */ }
    cargarFoto()
  })
  onCleanup(() => timer && clearInterval(timer))

  async function cargarFoto() {
    try { setFoto((await axios.get('/api/diagnostics/snapshot')).data) } catch { /* opcional */ }
  }

  function arrancarSondeo() {
    timer && clearInterval(timer)
    // Se piden solo los eventos NUEVOS, no el registro entero cada vez.
    timer = setInterval(async () => {
      try {
        const r = await axios.get('/api/diagnostics/events', { params: { since: ultimoSeq() } })
        if (r.data.events?.length) {
          cargarFoto()       // el estado del sistema cambia mientras se usa
          setEventos(prev => [...prev, ...r.data.events].slice(-800))
          setUltimoSeq(r.data.last_seq)
        }
      } catch { /* sondeo de fondo */ }
    }, 1200)
  }

  async function alternar() {
    const nuevo = !activo()
    setActivo(nuevo)
    try {
      await axios.put('/api/diagnostics', { enabled: nuevo })
      if (nuevo) { setEventos([]); setUltimoSeq(0); arrancarSondeo() }
      else { timer && clearInterval(timer); setEventos([]) }
    } catch { setActivo(!nuevo) }
  }

  async function limpiar() {
    try {
      await axios.delete('/api/diagnostics/events')
      setEventos([]); setUltimoSeq(0)
    } catch { /* nada crítico */ }
  }

  async function copiar() {
    try {
      const r = await axios.get('/api/diagnostics/export')
      await navigator.clipboard.writeText(r.data)
      setAviso(t('dg.copied')); setTimeout(() => setAviso(''), 2500)
    } catch { setAviso(t('dg.copy_error')); setTimeout(() => setAviso(''), 2500) }
  }

  async function descargar() {
    try {
      const r = await axios.get('/api/diagnostics/export')
      const { saveTextFile } = await import('../services/download.js')
      const res = await saveTextFile('andromeda-diagnostico.txt', r.data, 'text/plain')
      setAviso(res.ok ? t('dg.saved') : t('dg.copy_error'))
      setTimeout(() => setAviso(''), 2500)
    } catch { setAviso(t('dg.copy_error')); setTimeout(() => setAviso(''), 2500) }
  }

  const visibles = () => {
    const f = filtro()
    return f ? eventos().filter(e => e.category === f) : eventos()
  }

  const categorias = () => [...new Set(eventos().map(e => e.category))].sort()

  return (
    <div class="panel-page" style="max-width:1100px">
      {/* Aviso de que esto no va en la versión publicada. Un panel que expone
          prompts completos y variables de entorno no debe pasar desapercibido. */}
      <div style="display:flex;align-items:center;gap:8px;padding:9px 13px;margin-bottom:14px;border-radius:12px;background:rgba(251,191,36,.10);border:1px solid rgba(251,191,36,.28)">
        <span style="flex-shrink:0">🔧</span>
        <span style="font-size:var(--fs-xs);color:var(--amber);line-height:1.5">
          {t('dg.temporary')}
        </span>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <div>
          <h3 class="section-title">{t('dg.title')}</h3>
          <p class="section-sub" style="margin-bottom:0">{t('dg.desc')}</p>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <button class="btn" classList={{ 'btn-glass': !activo() }}
                  style={activo() ? 'background:var(--red);color:#fff' : ''}
                  onClick={alternar}>
            {activo() ? t('dg.stop') : t('dg.start')}
          </button>
        </div>
      </div>

      {/* Estado del sistema: responde a "¿está esto encendido?" de un vistazo,
          sin necesidad de activar el registro. */}
      <Show when={foto()}>
        <div class="card" style="padding:14px;margin-top:14px">
          <div style="font-size:var(--fs-sm);font-weight:600;margin-bottom:10px">
            {t('dg.state')}
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(178px,1fr));gap:8px">
            <For each={Object.entries(foto().capacidades)}>
              {([k, v]) => (
                <div style="display:flex;align-items:center;gap:7px;font-size:var(--fs-xs)">
                  <span style={`width:7px;height:7px;border-radius:50%;background:${v ? 'var(--green)' : 'var(--red)'};flex-shrink:0`} />
                  <span style="color:var(--text-2)">{t('dg.cap_' + k)}</span>
                </div>
              )}
            </For>
          </div>
          <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--glass-border);font-size:var(--fs-micro);color:var(--text-3);line-height:1.75;font-family:var(--mono)">
            <div>modelos: {foto().ollama.modelos.join(', ') || '(ninguno)'} · keep_alive: {foto().ollama.keep_alive}</div>
            <div>mcp: {foto().mcp.conectados.join(', ') || '(ninguno)'}</div>
            <div>searxng: {foto().buscador.instancia_activa || foto().buscador.searxng_propio || '(instancias públicas)'}</div>
            <div>workspace: {foto().entorno.workspace || '(sin configurar)'}</div>

            {/* Hardware detectado y qué parámetros produce: explica por qué la
                generación va como va, sin tener que suponerlo. */}
            <Show when={foto().hardware?.cpu}>
              <div style="margin-top:8px;color:var(--text-2)">
                hw: {foto().hardware.cpu} · {foto().hardware.nucleos} núcleos ·
                {' '}{foto().hardware.ram_gb}GB RAM · {foto().hardware.vram_gb}GB VRAM ·
                {' '}{foto().hardware.aceleracion}
              </div>
              <Show when={foto().hardware.opciones_calculadas}>
                <div>→ ollama: {JSON.stringify(foto().hardware.opciones_calculadas)}</div>
              </Show>
              <Show when={Object.keys(foto().hardware.recomendado_en_ollama || {}).length}>
                <div style="color:var(--amber)">
                  ⚠ conviene activar: {Object.entries(foto().hardware.recomendado_en_ollama).map(([k, v]) => `${k}=${v}`).join(' ')}
                </div>
              </Show>
            </Show>

            <Show when={foto().recursos?.memoria_proceso_mb}>
              <div style="margin-top:8px">
                recursos: {foto().recursos.memoria_proceso_mb}MB ·
                {' '}cpu {foto().recursos.cpu_proceso_pct}% ·
                {' '}{foto().recursos.hilos} hilos ·
                {' '}sistema {foto().recursos.memoria_sistema_pct}% ram
              </div>
            </Show>

            <Show when={Object.keys(foto().entorno.variables || {}).length}>
              <details style="margin-top:8px">
                <summary style="cursor:pointer;color:var(--text-2)">
                  {Object.keys(foto().entorno.variables).length} variables de entorno
                </summary>
                <div style="padding-left:12px;padding-top:4px">
                  <For each={Object.entries(foto().entorno.variables)}>
                    {([k, v]) => <div>{k}={String(v).slice(0, 70)}</div>}
                  </For>
                </div>
              </details>
            </Show>
          </div>
        </div>
      </Show>

      <Show when={activo()}>
        <div style="display:flex;align-items:center;gap:8px;margin-top:14px;flex-wrap:wrap">
          <button class="btn btn-glass" style="font-size:var(--fs-xs);padding:5px 11px" onClick={copiar}>
            ⎘ {t('dg.copy')}
          </button>
          <button class="btn btn-glass" style="font-size:var(--fs-xs);padding:5px 11px" onClick={descargar}>
            ↓ {t('dg.download')}
          </button>
          <button class="btn btn-glass" style="font-size:var(--fs-xs);padding:5px 11px" onClick={limpiar}>
            {t('dg.clear')}
          </button>
          <span style="flex:1" />
          <select value={filtro()} onChange={e => setFiltro(e.target.value)}
                  aria-label={t('dg.filter')}
                  style="background:var(--inset-surface);border:1px solid var(--glass-border);border-radius:9px;padding:5px 9px;font-size:var(--fs-xs);color:var(--text-1)">
            <option value="">{t('dg.all')} ({eventos().length})</option>
            <For each={categorias()}>{c => <option value={c}>{c}</option>}</For>
          </select>
          <Show when={aviso()}>
            <span style="font-size:var(--fs-xs);color:var(--green)">{aviso()}</span>
          </Show>
        </div>

        <div class="card" style="padding:0;margin-top:10px;max-height:60vh;overflow-y:auto">
          <Show when={visibles().length} fallback={
            <div class="empty-state">
              <div class="empty-state-icon">📡</div>
              <div class="empty-state-title">{t('dg.waiting')}</div>
              <div class="empty-state-desc">{t('dg.waiting_d')}</div>
            </div>
          }>
            <For each={visibles()}>
              {(e) => (
                <div style="border-bottom:1px solid var(--glass-border)">
                  <div onClick={() => setAbierto(abierto() === e.seq ? null : e.seq)}
                       style="display:flex;align-items:baseline;gap:9px;padding:7px 13px;cursor:pointer;font-family:var(--mono);font-size:var(--fs-micro)">
                    <span style="opacity:.5;flex-shrink:0">{ICONO[e.category] || '·'}</span>
                    <span style="color:var(--text-3);flex-shrink:0;width:66px">{e.category}</span>
                    <span style={`color:${COLOR[e.level]};flex:1;min-width:0`}>{e.event}</span>
                    <Show when={e.duration_ms != null}>
                      <span style="color:var(--text-3);flex-shrink:0">{e.duration_ms}ms</span>
                    </Show>
                    <Show when={e.detail || Object.keys(e.data || {}).length}>
                      <span style="opacity:.4;flex-shrink:0">{abierto() === e.seq ? '▾' : '▸'}</span>
                    </Show>
                  </div>
                  <Show when={abierto() === e.seq}>
                    <div style="padding:0 13px 11px 44px;font-family:var(--mono);font-size:var(--fs-micro);color:var(--text-3)">
                      <For each={Object.entries(e.data || {})}>
                        {([k, v]) => <div>{k}: {JSON.stringify(v)}</div>}
                      </For>
                      <Show when={e.detail}>
                        <pre style="white-space:pre-wrap;word-break:break-word;margin:7px 0 0;padding:9px;background:var(--inset-surface);border-radius:9px;max-height:340px;overflow-y:auto;color:var(--text-2)">{e.detail}</pre>
                      </Show>
                    </div>
                  </Show>
                </div>
              )}
            </For>
          </Show>
        </div>
      </Show>

      <Show when={!activo()}>
        <div class="card" style="padding:16px;margin-top:14px">
          <div style="font-size:var(--fs-sm);color:var(--text-2);line-height:1.65">
            {t('dg.off_explainer')}
          </div>
        </div>
      </Show>
    </div>
  )
}
