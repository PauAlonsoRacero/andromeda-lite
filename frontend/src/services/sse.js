/**
 * sse.js — Cliente SSE de Andromeda.
 *
 * Por qué fetch + ReadableStream y no EventSource:
 *   - EventSource no soporta POST (solo GET)
 *   - EventSource no permite headers personalizados
 *   - fetch + ReadableStream da control total sobre el stream
 *
 * Protocolo SSE del backend:
 *   data: {"chunk_id":"...","content":"token","is_final":false}\n\n
 *   data: {"chunk_id":"...","content":"...","is_final":true,"metadata":{...}}\n\n
 *   data: [DONE]\n\n
 */
import { t } from '../stores/i18n.js'


/**
 * Abre un stream SSE al backend de Andromeda.
 *
 * @param {object} params
 * @param {string} params.prompt         — Texto del usuario
 * @param {string} params.strategy       — Estrategia (default: 'auto')
 * @param {string[]} params.specialists  — Especialistas forzados (default: [])
 * @param {number} params.temperature    — Temperatura (default: 0.7)
 * @param {number} params.maxTokens      — Max tokens (default: 2048)
 * @param {function} params.onToken      — Callback(token, specialistId) por cada chunk
 * @param {function} params.onComplete   — Callback(metadata) al finalizar
 * @param {function} params.onError      — Callback(error) en caso de error
 *
 * @returns {function} cancel — llama a cancel() para abortar el stream
 */
/**
 * Reparte el texto recibido fotograma a fotograma.
 *
 * Llega a bloques (cada consulta trae todo lo generado desde la anterior); si se
 * pintara tal cual, el texto aparecería a saltos. Aquí se revela poco a poco, y
 * la velocidad se adapta a lo pendiente: con mucho acumulado acelera, para no
 * quedarse nunca más de ~0,3 s por detrás de lo que ya ha generado el modelo.
 */
function createSmoother(emit) {
  let queue = ''
  let spec = null
  let raf = null
  let onDrained = null
  const tick = () => {
    if (!queue) {
      raf = null
      if (onDrained) { const f = onDrained; onDrained = null; f() }
      return
    }
    const n = Math.max(2, Math.ceil(queue.length / 18))
    emit?.(queue.slice(0, n), spec)
    queue = queue.slice(n)
    raf = requestAnimationFrame(tick)
  }
  return {
    push(text, specialist) {
      queue += text
      if (specialist) spec = specialist
      if (!raf) raf = requestAnimationFrame(tick)
    },
    flush() {
      if (!queue && !raf) return Promise.resolve()
      return new Promise(resolve => { onDrained = resolve; if (!raf) raf = requestAnimationFrame(tick) })
    },
    cancel() { if (raf) cancelAnimationFrame(raf); raf = null; queue = '' },
  }
}

export function openStream({
  prompt,
  strategy = 'auto',
  specialists = [],
  temperature = 0.7,
  // 8192: con 2048 una página web completa se cortaba a mitad del archivo
  // y se guardaba un HTML truncado. El backend lo ajusta al hardware.
  maxTokens = 8192,
  parallel_policy = 'auto',
  max_parallel = null,
  specialist_levels = {},
  force_model = null,
  project_id = null,
  project_name = null,
  project_instructions = null,
  images = [],
  incognito = false,
  conversation_history = [],
  onToken,
  onComplete,
  onError,
  onPlaceholder,
}) {
  const controller = new AbortController()

  // En el binario de escritorio (pywebview / WKWebView en macOS), fetch no
  // entrega el body de forma incremental: response.body.getReader() se queda
  // esperando y el chat nunca muestra tokens. En ese entorno pedimos la
  // respuesta completa de una vez (stream=false) y la mostramos al llegar.
  const isDesktop = /pywebview/i.test(navigator.userAgent)
    || (window.pywebview != null)
    || (window.__ANDROMEDA_DESKTOP__ === true)

  if (isDesktop) {
    // Escritorio: WKWebView no lee respuestas a trozos, así que el backend
    // genera en streaming y aquí se consulta el progreso cada ~100 ms. El
    // suavizador reparte el texto nuevo fotograma a fotograma para que se vea
    // escribirse de forma continua, no a saltos.
    let stopped = false
    let jobId = null
    const headers = { 'Content-Type': 'application/json' }
    try {
      const saved = JSON.parse(localStorage.getItem('andromeda_session') || 'null')
      if (saved?.token) headers['X-Andromeda-Token'] = saved.token
    } catch { /* sin sesión guardada */ }
    const smoother = createSmoother(onToken)
    const sleep = (ms) => new Promise(r => setTimeout(r, ms))

    ;(async () => {
      try {
        onPlaceholder?.(t('phase.thinking'))
        const response = await fetch('/api/chat/jobs', {
          method: 'POST', headers, signal: controller.signal,
          body: JSON.stringify({
            prompt, strategy, specialists, temperature, max_tokens: maxTokens,
            stream: false, incognito, web_search: !incognito, parallel_policy,
            images, max_parallel, specialist_levels, force_model,
            project_id, project_name, project_instructions,
            // El historial se recibía como parámetro pero NO se enviaba: la IA
            // no recordaba nada de lo hablado en el mismo chat, así que un
            // "búscalo, por favor" no tenía a qué referirse.
            conversation_history,
          }),
        })
        if (!response.ok) {
          let err; try { err = await response.json() } catch { err = { message: `HTTP ${response.status}` } }
          onError?.(err); return
        }
        jobId = (await response.json()).job_id
        let offset = 0
        let lastPhase = null
        while (!stopped) {
          const r = await fetch(`/api/chat/jobs/${jobId}?since=${offset}`, { headers, signal: controller.signal })
          if (!r.ok) { onError?.({ message: t('err.generic') }); return }
          const d = await r.json()
          if (d.delta) {
            smoother.push(d.delta, d.specialist)
            offset = d.offset
          } else if (offset === 0 && d.phase !== lastPhase) {
            // Mientras no haya texto, la frase refleja lo que está pasando de verdad.
            lastPhase = d.phase
            onPlaceholder?.(d.phase === 'thinking' && d.phrase ? d.phrase : t('phase.' + d.phase))
          }
          if (d.done) {
            await smoother.flush()
            if (d.error && offset === 0) { onError?.(d.error); return }
            onComplete?.({ ...(d.meta || {}) })
            return
          }
          // Antes del primer token se consulta con menos frecuencia.
          await sleep(offset === 0 ? 250 : 90)
        }
      } catch (e) {
        if (e.name !== 'AbortError') onError?.({ message: e.message || t('err.no_connection') })
      }
    })()
    return () => {
      stopped = true
      smoother.cancel()
      controller.abort()
      if (jobId) fetch(`/api/chat/jobs/${jobId}`, { method: 'DELETE', headers }).catch(() => {})
    }
  }

  // Lanzar la petición de forma async sin bloquear
  ;(async () => {
    try {
      // Cabeceras: incluir el token de sesión (fetch no usa los defaults de
      // axios, así que hay que añadirlo a mano o el chat da 401 con auth activa).
      const headers = { 'Content-Type': 'application/json' }
      try {
        const saved = JSON.parse(localStorage.getItem('andromeda_session') || 'null')
        if (saved?.token) headers['X-Andromeda-Token'] = saved.token
      } catch { /* sin sesión */ }

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          prompt,
          strategy,
          specialists,
          temperature,
          max_tokens: maxTokens,
          stream: true,
          incognito,
          web_search: !incognito,
          parallel_policy,
          images,
          max_parallel,
          specialist_levels,
          force_model,
          project_id, project_name, project_instructions,
          conversation_history,
        }),
        signal: controller.signal,
      })

      // El backend retornó un error HTTP
      if (!response.ok) {
        let errorData
        try { errorData = await response.json() }
        catch { errorData = { message: `HTTP ${response.status}` } }
        onError?.(errorData)
        return
      }

      // Leer el stream de respuesta
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // Decodificar el chunk de bytes recibido
        buffer += decoder.decode(value, { stream: true })

        // Las líneas SSE terminan en \n\n — procesar las completas
        const lines = buffer.split('\n')
        // La última línea puede estar incompleta — guardarla para el próximo chunk
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue

          const data = trimmed.slice(6)   // quitar el "data: "

          // Señal de fin del stream
          if (data === '[DONE]') return

          try {
            const chunk = JSON.parse(data)

            if (chunk.is_final) {
              // Último chunk — contiene los metadatos completos
              onComplete?.(chunk.metadata || {})
            } else if (chunk.metadata?.phase) {
              // Fase real del proceso (p. ej. buscando en internet)
              onPlaceholder?.(t('phase.' + chunk.metadata.phase))
            } else if (chunk.metadata?.placeholder) {
              // Frase de espera mientras el modelo carga (antes del primer token)
              onPlaceholder?.(chunk.metadata.placeholder, chunk.metadata.power_level)
            } else if (chunk.content) {
              // Chunk de tokens — actualizar la UI
              const stage = chunk.metadata?.stage || null
              onToken?.(chunk.content, chunk.specialist_id, stage)
            }
          } catch {
            // Línea malformada — ignorar silenciosamente
          }
        }
      }
    } catch (err) {
      // Ignorar errores de abort (el usuario canceló)
      if (err.name !== 'AbortError') {
        // Mensaje específico según el tipo de fallo
        let msg = err?.message || t('err.generic')
        if (err instanceof TypeError && /fetch/i.test(msg)) {
          msg = 'No se pudo conectar con el backend (¿está corriendo en :8000?)'
        }
        onError?.({ message: msg })
      }
    }
  })()

  // Retornar función para cancelar el stream desde la UI
  return () => controller.abort()
}
