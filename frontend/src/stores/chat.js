/**
 * chat.js — Estado global del chat con historial persistente.
 *
 * Novedad: historial de conversaciones en localStorage.
 * Cada conversación tiene un ID, nombre auto-generado, y lista de mensajes.
 * El usuario puede cambiar entre conversaciones desde el SidePanel.
 */

import { createSignal } from 'solid-js'
import { createStore, produce } from 'solid-js/store'

// ── Historial de conversaciones ───────────────────────────────────────────────
const STORAGE_KEY = 'andromeda_conversations'
const MAX_CONVERSATIONS = 20

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveConversations(convs) {
  const slice = convs.slice(0, MAX_CONVERSATIONS)
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(slice)) }
  catch {}
  // Respaldo en disco vía backend (en el binario localStorage no persiste).
  try {
    fetch(`/api/uistate/${STORAGE_KEY}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: slice }),
    }).catch(() => {})
  } catch {}
}

/** Rehidrata las conversaciones desde el backend al arrancar. */
export async function hydrateConversationsFromBackend() {
  try {
    const r = await fetch(`/api/uistate/${STORAGE_KEY}`)
    if (!r.ok) return
    const { value } = await r.json()
    if (Array.isArray(value) && value.length) {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)) } catch {}
      setConversations(value)
    }
  } catch {}
}

function generateTitle(firstUserMessage) {
  if (!firstUserMessage) return 'Nueva conversación'
  return firstUserMessage.slice(0, 42) + (firstUserMessage.length > 42 ? '…' : '')
}

// ── Estado principal ──────────────────────────────────────────────────────────
const [chatState, setChatState] = createStore({
  messages:       [],
  isStreaming:    false,
  error:          null,
  conversationId: null,
})

// Signal para el stream activo (token a token)
const [streamContent, setStreamContent]     = createSignal('')
const [streamRaw, setStreamRaw]             = createSignal('')   // respuestas individuales (antes de IA de salida)
const [outputStarted, setOutputStarted]     = createSignal(false)
const [streamProgress, setStreamProgress]   = createSignal(null) // {working:[ids], done, total} en multi-IA
const [streamPlaceholder, setStreamPlaceholder] = createSignal(null) // frase de espera mientras carga
const [streamSpecialist, setStreamSpecialist] = createSignal(null)
const [streamSpecialists, setStreamSpecialists] = createSignal([])

// Historial de conversaciones
const [conversations, setConversations] = createSignal(loadConversations())
const [activeConvId, setActiveConvId]   = createSignal(null)

// ── Acciones ──────────────────────────────────────────────────────────────────

export function addUserMessage(content) {
  // Si no hay conversación activa, crear una nueva
  if (!activeConvId()) {
    newConversation()
  }
  setChatState('messages', msgs => [
    ...msgs,
    { id: crypto.randomUUID(), role: 'user', content, timestamp: new Date().toISOString(), metadata: null }
  ])
}

export function startAssistantMessage(requestId) {
  setChatState('isStreaming', true)
  setChatState('messages', msgs => [
    ...msgs,
    { id: requestId, role: 'assistant', content: '', streaming: true, timestamp: new Date().toISOString(), metadata: null }
  ])
  setStreamContent('')
  setStreamSpecialist(null)
}

export function appendToken(token, specialistId, stage) {
  // Multi-IA: mientras las IAs trabajan, mostramos progreso (no tokens crudos).
  if (stage === 'working') {
    setStreamProgress(prev => {
      const working = prev?.working || []
      const total = prev?.total || 0
      return { working: working.includes(specialistId) ? working : [...working, specialistId],
               done: prev?.done || 0, total }
    })
    if (specialistId) setStreamSpecialists(prev => prev.includes(specialistId) ? prev : [...prev, specialistId])
    return
  }
  if (stage === 'progress') {
    return  // actualización de "X de N listas" — el indicador ya lo refleja
  }

  // La respuesta final limpia (IA de salida o fusión) reemplaza el indicador.
  if (stage === 'output_ai' || stage === 'fusion') {
    if (!outputStarted()) {
      setOutputStarted(true)
      setStreamProgress(null)     // quitar el indicador de "trabajando"
      setStreamContent('')        // empezar limpio
    }
    setStreamContent(prev => prev + token)
    return
  }

  // 1 IA: streaming normal token a token.
  if (streamPlaceholder()) setStreamPlaceholder(null)  // primer token: quitar la frase de espera
  setStreamContent(prev => prev + token)
  if (specialistId) {
    setStreamSpecialist(specialistId)
    setStreamSpecialists(prev => prev.includes(specialistId) ? prev : [...prev, specialistId])
  }
}

export function finalizeMessage(requestId, metadata) {
  const content = streamContent()
  // Garantizar que las medallas de especialistas no desaparezcan:
  // si el backend no mandó specialists_used, usar los acumulados durante el stream
  const seen = streamSpecialists()
  const finalMeta = { ...metadata }
  if (!finalMeta.specialists_used || finalMeta.specialists_used.length === 0) {
    if (seen.length > 0) finalMeta.specialists_used = seen
  }
  setChatState(produce(state => {
    const msg = state.messages.find(m => m.id === requestId)
    if (msg) {
      msg.content = content; msg.streaming = false; msg.metadata = finalMeta
      const raw = streamRaw()
      if (raw && raw.trim()) msg.rawResponses = raw   // respuestas individuales (desplegable)
    }
  }))
  setChatState('isStreaming', false)
  setStreamContent('')
  setStreamSpecialist(null)
  setStreamSpecialists([])
  // Persistir conversación actualizada
  _persistCurrentConversation()
}

export function failMessage(requestId, errorMsg) {
  setChatState(produce(state => {
    const msg = state.messages.find(m => m.id === requestId)
    if (msg) { msg.content = errorMsg; msg.streaming = false; msg.error = true }
  }))
  setChatState('isStreaming', false)
  setStreamContent('')
  setStreamSpecialist(null)
}

export function clearMessages() {
  setChatState('messages', [])
  setChatState('isStreaming', false)
  setStreamContent('')
  setActiveConvId(null)
  setChatState('conversationId', null)
}

// ── Gestión de conversaciones ─────────────────────────────────────────────────

export function newConversation() {
  // Si ya hay una conversación vacía, cárgala en lugar de crear otra
  const emptyConv = conversations().find(c => c.messages.length === 0)
  if (emptyConv) {
    setActiveConvId(emptyConv.id)
    setChatState('conversationId', emptyConv.id)
    setChatState('messages', [])
    return emptyConv.id
  }

  const id = crypto.randomUUID()
  setActiveConvId(id)
  setChatState('conversationId', id)
  setChatState('messages', [])
  const conv = { id, title: 'Nueva conversación', createdAt: new Date().toISOString(), messages: [] }
  const updated = [conv, ...conversations()]
  setConversations(updated)
  saveConversations(updated)
  return id
}

export function loadConversation(id) {
  const conv = conversations().find(c => c.id === id)
  if (!conv) return
  setActiveConvId(id)
  setChatState('conversationId', id)
  setChatState('messages', conv.messages || [])
  setChatState('isStreaming', false)
  setStreamContent('')
  setStreamRaw('')
  setOutputStarted(false)
  setStreamProgress(null)
}

export function deleteConversation(id) {
  const updated = conversations().filter(c => c.id !== id)
  setConversations(updated)
  saveConversations(updated)
  if (activeConvId() === id) clearMessages()
}

export function renameConversation(id, title) {
  setConversations(prev => prev.map(c => c.id === id ? { ...c, title } : c))
  saveConversations(conversations())
}

export function toggleFavorite(id) {
  const updated = conversations().map(c => c.id === id ? { ...c, favorite: !c.favorite } : c)
  setConversations(updated)
  saveConversations(updated)
}

/** Respaldo: descarga todas las conversaciones como archivo JSON. */
export async function exportConversations() {
  const { default: axios } = await import('axios')
  // Intentar primero el backend (funciona en el binario de escritorio, donde la
  // descarga de Blobs del navegador no está disponible). Si falla, caer al Blob.
  try {
    const r = await axios.post('/api/backup/export', { conversations: conversations() })
    if (r.data?.success) {
      return { method: 'file', path: r.data.path, conversations: r.data.conversations, memories: r.data.memories }
    }
  } catch {}
  // Fallback web: descarga por Blob
  let memories = []
  try {
    const r = await axios.get('/api/memory/list')
    memories = r.data.memories || []
  } catch {}
  const data = {
    app: 'andromeda', version: 2, exported_at: new Date().toISOString(),
    conversations: conversations(), memories,
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `andromeda-backup-${new Date().toISOString().slice(0,10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  return { method: 'download' }
}

/** Restaura conversaciones desde un archivo de respaldo. Fusiona sin duplicar
 *  por id; las importadas que ya existen se omiten. Devuelve cuántas añadió. */
export async function importConversations(jsonText) {
  let parsed
  try { parsed = JSON.parse(jsonText) } catch { throw new Error('Archivo no válido') }
  const incoming = Array.isArray(parsed) ? parsed : parsed.conversations
  if (!Array.isArray(incoming)) throw new Error('El archivo no contiene conversaciones')
  const existingIds = new Set(conversations().map(c => c.id))
  const toAdd = incoming.filter(c => c && c.id && !existingIds.has(c.id))
  const merged = [...toAdd, ...conversations()].slice(0, MAX_CONVERSATIONS)
  setConversations(merged)
  saveConversations(merged)
  // Restaurar memorias si el backup las incluye (formato v2+)
  let memAdded = 0
  if (parsed && Array.isArray(parsed.memories) && parsed.memories.length) {
    try {
      const { default: axios } = await import('axios')
      for (const m of parsed.memories) {
        if (!m || !m.content) continue
        await axios.post('/api/memory', {
          content: m.content,
          source: m.source || 'import',
          category: m.category || 'general',
        })
        memAdded++
      }
    } catch {}
  }
  return { conversations: toAdd.length, memories: memAdded }
}

function _persistCurrentConversation() {
  const id = activeConvId()
  if (!id) return
  const msgs = chatState.messages.filter(m => !m.streaming && m.content)
  if (msgs.length === 0) return
  // Auto-title from first user message
  const firstUser = msgs.find(m => m.role === 'user')
  const title = firstUser ? generateTitle(firstUser.content) : 'Nueva conversación'
  // Capturar el array actualizado y guardarlo (evita el bug de timing de signals)
  const updated = conversations().map(c =>
    c.id === id ? { ...c, title, messages: msgs, updatedAt: new Date().toISOString() } : c
  )
  // Si la conversación no existe aún en el array, añadirla
  if (!updated.find(c => c.id === id)) {
    updated.unshift({ id, title, messages: msgs, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() })
  }
  setConversations(updated)
  saveConversations(updated)
}

export function showPlaceholder(phrase, powerLevel) {
  setStreamPlaceholder(phrase || null)
  if (powerLevel) setStreamSpecialist(null)
}

export { chatState, streamContent, streamSpecialist, conversations, activeConvId, streamRaw, outputStarted, streamProgress, streamPlaceholder }
