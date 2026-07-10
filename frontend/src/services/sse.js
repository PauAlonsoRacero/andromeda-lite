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
export function openStream({
  prompt,
  strategy = 'auto',
  specialists = [],
  temperature = 0.7,
  maxTokens = 2048,
  parallel_policy = 'auto',
  max_parallel = null,
  specialist_levels = {},
  force_model = null,
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
    ;(async () => {
      try {
        const headers = { 'Content-Type': 'application/json' }
        try {
          const saved = JSON.parse(localStorage.getItem('andromeda_session') || 'null')
          if (saved?.token) headers['X-Andromeda-Token'] = saved.token
        } catch {}
        onPlaceholder?.('Pensando…')
        const response = await fetch('/api/chat', {
          method: 'POST', headers, signal: controller.signal,
          body: JSON.stringify({
            prompt, strategy, specialists, temperature, max_tokens: maxTokens,
            stream: false, incognito, web_search: !incognito, parallel_policy,
            images, max_parallel, specialist_levels, force_model,
          }),
        })
        if (!response.ok) {
          let err; try { err = await response.json() } catch { err = { message: `HTTP ${response.status}` } }
          onError?.(err); return
        }
        const data = await response.json()
        // El JSON completo trae la respuesta final y metadata.
        const text = data.response || data.content || ''
        const specId = (data.specialists_used && data.specialists_used[0]) || null
        if (text) onToken?.(text, specId)
        onComplete?.({
          power_tier: data.power_tier, power_reason: data.power_reason,
          models_used: data.models_used, latency_ms: data.latency_ms,
          ...data,
        })
      } catch (e) {
        if (e.name !== 'AbortError') onError?.({ message: e.message || 'Error de red' })
      }
    })()
    return () => controller.abort()
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
        let msg = err?.message || 'Error desconocido'
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
