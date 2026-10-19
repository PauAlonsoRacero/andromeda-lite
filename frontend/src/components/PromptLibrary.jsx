/**
 * PromptLibrary.jsx — Biblioteca personal de prompts.
 * Modal que permite guardar, buscar y reutilizar prompts favoritos.
 * Los prompts se persisten en el backend (SQLite).
 */
import PromptCatalog from './PromptCatalog.jsx'
import { Portal } from 'solid-js/web'
import { createSignal, onMount, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'

export default function PromptLibrary({ onSelect, onClose }) {
  const [prompts, setPrompts]     = createSignal([])
  const [loading, setLoading]     = createSignal(true)
  const [filter, setFilter]       = createSignal('')
  // El catálogo va primero: la biblioteca propia empieza vacía y antes el
  // usuario abría una lista sin nada.
  const [tab, setTab]             = createSignal('catalog')
  const [showAdd, setShowAdd]     = createSignal(false)
  const [newTitle, setNewTitle]   = createSignal('')
  const [newContent, setNewContent] = createSignal('')
  const [saving, setSaving]       = createSignal(false)

  onMount(loadPrompts)

  async function loadPrompts() {
    setLoading(true)
    try {
      const r = await axios.get('/api/chat/prompts')
      setPrompts(r.data.prompts || [])
    } catch { /* carga de fondo: un fallo puntual no debe molestar al usuario */ }
    finally { setLoading(false) }
  }

  async function savePrompt() {
    if (!newContent().trim()) return
    setSaving(true)
    try {
      await axios.post('/api/chat/prompts', {
        title: newTitle() || newContent().slice(0, 40),
        content: newContent(),
      })
      await loadPrompts()
      setNewTitle(''); setNewContent(''); setShowAdd(false)
    } catch { /* carga de fondo: un fallo puntual no debe molestar al usuario */ }
    finally { setSaving(false) }
  }

  async function deletePrompt(id, e) {
    e.stopPropagation()
    await axios.delete(`/api/chat/prompts/${id}`)
    setPrompts(prev => prev.filter(p => p.id !== id))
  }

  async function usePrompt(prompt) {
    await axios.post(`/api/chat/prompts/${prompt.id}/use`).catch(() => {})
    onSelect(prompt.content)
    onClose()
  }

  const filtered = () => {
    const q = filter().toLowerCase()
    if (!q) return prompts()
    return prompts().filter(p =>
      p.title?.toLowerCase().includes(q) || p.content.toLowerCase().includes(q)
    )
  }

  return (
    <Portal>
    <div class="settings-overlay" onClick={onClose}>
      <div class="settings-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div class="settings-title">
          <span>{t('ui2.prompt_lib')}</span>
          <button onClick={onClose} style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:var(--fs-lg);line-height:1" aria-label="cerrar">✕</button>
        </div>

        <div class="pcat-tabs" role="tablist">
          <button role="tab" class="pcat-chip" classList={{ on: tab() === 'catalog' }}
                  onClick={() => setTab('catalog')}>{t('pcat.catalog')}</button>
          <button role="tab" class="pcat-chip" classList={{ on: tab() === 'mine' }}
                  onClick={() => setTab('mine')}>{t('pcat.mine')}</button>
        </div>
        <Show when={tab() === 'catalog'}>
          <PromptCatalog onUse={(body) => onSelect?.(body)} maxHeight="55vh" />
        </Show>
        <Show when={tab() === 'mine'}>
        {/* Search + Add */}
        <div style="display:flex;gap:8px;margin-bottom:14px">
          <input aria-label={t('pl.ph_search')}
            class="g-input"
            placeholder={t('pl.ph_search')}
            value={filter()}
            onInput={e => setFilter(e.target.value)}
            style="flex:1"
          />
          <button class="btn btn-teal" onClick={() => setShowAdd(v => !v)}>
            {showAdd() ? '✕' : '+ Nuevo'}
          </button>
        </div>

        {/* New prompt form */}
        <Show when={showAdd()}>
          <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);padding:14px;margin-bottom:14px;display:flex;flex-direction:column;gap:8px">
            <input aria-label={t('pl.ph_title')}
              class="g-input"
              placeholder={t('pl.ph_title')}
              value={newTitle()}
              onInput={e => setNewTitle(e.target.value)}
            />
            <textarea
              class="g-input"
              placeholder={t('pl.ph_write')}
              value={newContent()}
              onInput={e => setNewContent(e.target.value)}
              rows={4}
              style="resize:vertical;font-family:var(--mono)"
            />
            <div style="display:flex;gap:8px;justify-content:flex-end">
              <button class="btn btn-ghost" onClick={() => setShowAdd(false)}>{t('btn.cancel')}</button>
              <button class="btn btn-primary" onClick={savePrompt} disabled={saving() || !newContent().trim()}>
                {saving() ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </Show>

        {/* Prompt list */}
        <Show when={loading()}>
          <div style="text-align:center;padding:30px;color:var(--text-3)">
            <span class="spin" /> Cargando...
          </div>
        </Show>

        <Show when={!loading() && filtered().length === 0}>
          <div style="text-align:center;padding:40px;color:var(--text-3)">
            <div style="margin-bottom:8px;opacity:.3;display:flex;justify-content:center"><svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></div>
            <div>{filter() ? 'Sin resultados' : 'Sin prompts guardados'}</div>
            <div style="font-size:var(--fs-xs);margin-top:4px">
              {!filter() && 'Guarda tus prompts frecuentes para reutilizarlos'}
            </div>
          </div>
        </Show>

        <div style="display:flex;flex-direction:column;gap:6px;max-height:360px;overflow-y:auto">
          <For each={filtered()}>
            {(p) => (
              <div
                style="padding:12px 14px;border-radius:var(--r-sm);background:var(--surface);border:1px solid var(--border);cursor:pointer;transition:all .12s;display:flex;align-items:flex-start;gap:10px"
                onClick={() => usePrompt(p)}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
                onMouseLeave={e => e.currentTarget.style.background = 'var(--surface)'}
              >
                <div style="flex:1;min-width:0">
                  <div style="font-size:var(--fs-sm);font-weight:600;color:var(--text-1);margin-bottom:3px">
                    {p.title || p.content.slice(0, 40)}
                  </div>
                  <div style="font-size:var(--fs-xs);color:var(--text-3);font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    {p.content}
                  </div>
                  <Show when={p.use_count > 0}>
                    <div style="font-size:var(--fs-micro);color:var(--text-3);margin-top:4px">
                      Usado {p.use_count} {p.use_count === 1 ? 'vez' : 'veces'}
                    </div>
                  </Show>
                </div>
                <button
                  onClick={e => deletePrompt(p.id, e)}
                  style="background:none;border:none;color:var(--red);cursor:pointer;font-size:var(--fs-sm);opacity:.4;padding:2px;flex-shrink:0;transition:opacity .12s"
                  onMouseEnter={e => e.target.style.opacity = '1'}
                  onMouseLeave={e => e.target.style.opacity = '.4'}
                  title={t('pl.delete')}
                >✕</button>
              </div>
            )}
          </For>
        </div>
        </Show>
      </div>
    </div>
    </Portal>
  )
}
