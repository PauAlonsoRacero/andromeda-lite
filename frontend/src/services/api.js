/**
 * api.js — Cliente HTTP de Andromeda.
 * Todas las llamadas al backend FastAPI pasan por aquí.
 * Usa axios con base URL /api (el proxy de Vite lo redirige al backend).
 */

import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 130_000,   // 130s — mayor que el timeout de Ollama (120s)
  headers: { 'Content-Type': 'application/json' },
})

// ── Chat ──────────────────────────────────────────────────────────────────────

/**
 * Envía un prompt al orquestador (modo no-streaming).
 * Para streaming, usar sse.js directamente.
 */
export const sendChat = (prompt, strategy = 'auto', specialists = [], temperature = 0.7, maxTokens = 2048) =>
  api.post('/chat', { prompt, strategy, specialists, temperature, max_tokens: maxTokens, stream: false })
    .then(r => r.data)

/** Lista de estrategias disponibles con info de cada una */
export const getStrategies = () =>
  api.get('/chat/strategies').then(r => r.data)

/** Historial de las últimas peticiones */
export const getChatHistory = (limit = 50) =>
  api.get(`/chat/history?limit=${limit}`).then(r => r.data)

// ── Modelos / Especialistas ───────────────────────────────────────────────────

/** Todos los especialistas (activos e inactivos) */
export const getAllModels = () =>
  api.get('/models').then(r => r.data)

/** Solo los especialistas activos y configurados */
export const getActiveModels = () =>
  api.get('/models/active').then(r => r.data)

/** Resumen de estado + ping a Ollama */
export const getModelsStatus = () =>
  api.get('/models/status').then(r => r.data)

/** Actualizar modelo de un especialista en runtime */
export const updateModel = (specialistId, modelName, active = true) =>
  api.put(`/models/${specialistId}`, { model_name: modelName, active }).then(r => r.data)

/** Probar que un especialista responde */
export const testSpecialist = (specialistId) =>
  api.post(`/models/${specialistId}/test`).then(r => r.data)

// ── Health ────────────────────────────────────────────────────────────────────

/** Estado general del sistema */
export const getHealth = () =>
  api.get('/health').then(r => r.data).catch(err => err.response?.data || { status: 'down' })

/** Hardware detectado completo */
export const getHardware = () =>
  api.get('/health/hardware').then(r => r.data)

/** Política de hardware activa */
export const getPolicy = () =>
  api.get('/health/policy').then(r => r.data)

// ── Traces ────────────────────────────────────────────────────────────────────

/** Últimos N traces */
export const getTraces = (limit = 20) =>
  api.get(`/traces?limit=${limit}`).then(r => r.data)

/** Trace completo de un request específico */
export const getTrace = (requestId) =>
  api.get(`/traces/${requestId}`).then(r => r.data)

/** Métricas agregadas de observabilidad */
export const getMetrics = () =>
  api.get('/traces/metrics').then(r => r.data)
