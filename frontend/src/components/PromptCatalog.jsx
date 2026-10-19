/**
 * PromptCatalog.jsx — Explorador del catálogo de prompts prefabricados.
 *
 * Se usa en el chat (para insertar uno) y en Configuración (para guardarlos en
 * la biblioteca propia). Los [corchetes] marcan lo que hay que rellenar.
 */
import { createSignal, createMemo, createEffect, For, Show } from 'solid-js'
import axios from 'axios'
import { catalogFor } from '../data/promptCatalog.js'
import { t, lang } from '../stores/i18n.js'

export default function PromptCatalog(props) {
  const [q, setQ] = createSignal('')
  const [cat, setCat] = createSignal('')
  const [guardado, setGuardado] = createSignal('')

  // Catálogo en el idioma de la interfaz; cambia solo si se cambia el idioma.
  const catalogo = createMemo(() => catalogFor(lang()))
  createEffect(() => { lang(); setCat('') })   // al cambiar de idioma, sin filtro de categoría
  const lista = createMemo(() => {
    const texto = q().trim().toLowerCase()
    return catalogo().prompts.filter(p =>
      (!cat() || p.cat === cat()) &&
      (!texto || p.title.toLowerCase().includes(texto) || p.body.toLowerCase().includes(texto)))
  })

  async function guardar(p) {
    try {
      await axios.post('/api/chat/prompts', { title: p.title, content: p.body, tags: [p.cat] })
      setGuardado(p.title); setTimeout(() => setGuardado(''), 2000)
    } catch { /* la biblioteca propia no está disponible: el catálogo sigue usable */ }
  }

  return (
    <div class="pcat">
      <input class="pcat-search" type="search" placeholder={t('pcat.search')} value={q()}
             onInput={e => setQ(e.currentTarget.value)} aria-label={t('pcat.search')} />
      <div class="pcat-cats">
        <button class="pcat-chip" classList={{ on: !cat() }} onClick={() => setCat('')}>
          {t('pcat.all')} ({catalogo().prompts.length})
        </button>
        <For each={catalogo().categories}>
          {(c) => <button class="pcat-chip" classList={{ on: cat() === c }} onClick={() => setCat(c)}>{c}</button>}
        </For>
      </div>
      <div class="pcat-list" style={props.maxHeight ? `max-height:${props.maxHeight}` : ''}>
        <Show when={lista().length} fallback={<div class="pcat-empty">{t('pcat.none')}</div>}>
          <For each={lista()}>
            {(p) => (
              <div class="pcat-item">
                <div class="pcat-item-head">
                  <span class="pcat-title">{p.title}</span>
                  <span class="pcat-tag">{p.cat}</span>
                </div>
                <div class="pcat-body">{p.body}</div>
                <div class="pcat-actions">
                  <Show when={props.onUse}>
                    <button class="btn btn-primary pcat-btn" onClick={() => props.onUse(p.body)}>{t('pcat.use')}</button>
                  </Show>
                  <button class="btn btn-glass pcat-btn" onClick={() => guardar(p)}>
                    {guardado() === p.title ? '✓ ' + t('pcat.saved') : t('pcat.save')}
                  </button>
                </div>
              </div>
            )}
          </For>
        </Show>
      </div>
    </div>
  )
}
