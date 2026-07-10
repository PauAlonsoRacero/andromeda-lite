/**
 * ChatsListPanel.jsx — Pantalla con todos los chats, buscador y favoritos.
 */
import { createSignal, createMemo, For, Show } from 'solid-js'
import { conversations, loadConversation, deleteConversation, toggleFavorite, newConversation } from '../stores/chat.js'
import { t } from '../stores/i18n.js'

export default function ChatsListPanel(props) {
  const [query, setQuery] = createSignal('')
  const [filter, setFilter] = createSignal('all')  // all | favorites

  const filtered = createMemo(() => {
    let list = conversations()
    if (filter() === 'favorites') list = list.filter(c => c.favorite)
    const q = query().toLowerCase().trim()
    if (q) list = list.filter(c => (c.title || '').toLowerCase().includes(q))
    return list
  })

  function open(id) { loadConversation(id); props.onOpen?.() }

  return (
    <div class="panel-page" style="max-width:800px">
      <div class="panel-page-header">
        <div>
          <div class="panel-page-title">Chats</div>
          <div class="panel-page-sub">{conversations().length} conversaciones</div>
        </div>
        <button class="btn btn-primary" onClick={() => { newConversation(); props.onOpen?.() }}>{t('cl.new_conv')}</button>
      </div>

      {/* Buscador */}
      <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap">
        <div style="flex:1;min-width:200px;position:relative">
          <span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--text-3);font-size:14px">⌕</span>
          <input class="g-input" placeholder={t('cl.ph_search')} value={query()}
            onInput={e => setQuery(e.target.value)}
            style="width:100%;padding-left:38px" />
        </div>
        <div style="display:flex;gap:4px;background:var(--glass-bright);border-radius:12px;padding:4px">
          <button onClick={() => setFilter('all')}
            style={`padding:8px 16px;border-radius:9px;border:none;cursor:pointer;font-size:13px;font-weight:600;font-family:var(--font);transition:all 0.15s;background:${filter()==='all'?'var(--glass-hi)':'transparent'};color:${filter()==='all'?'var(--text-1)':'var(--text-3)'}`}>
            Todos
          </button>
          <button onClick={() => setFilter('favorites')}
            style={`padding:8px 16px;border-radius:9px;border:none;cursor:pointer;font-size:13px;font-weight:600;font-family:var(--font);transition:all 0.15s;background:${filter()==='favorites'?'var(--glass-hi)':'transparent'};color:${filter()==='favorites'?'var(--text-1)':'var(--text-3)'}`}>
            ★ Favoritos
          </button>
        </div>
      </div>

      {/* Lista */}
      <Show when={filtered().length > 0} fallback={
        <div class="card" style="text-align:center;padding:48px">
          <div style="font-size:40px;opacity:0.2;margin-bottom:16px">{filter()==='favorites'?'★':'◇'}</div>
          <div style="font-size:15px;font-weight:600;margin-bottom:6px">
            {query() ? 'Sin resultados' : filter()==='favorites' ? 'Sin favoritos' : 'Sin conversaciones'}
          </div>
          <div style="font-size:13px;color:var(--text-3)">
            {query() ? 'Prueba otra búsqueda' : 'Empieza una nueva conversación'}
          </div>
        </div>
      }>
        <div style="display:flex;flex-direction:column;gap:8px">
          <For each={filtered()}>
            {(c) => (
              <div class="card" style="margin-bottom:0;padding:16px 18px;cursor:pointer;display:flex;align-items:center;gap:14px"
                onClick={() => open(c.id)}
                onMouseEnter={e => e.currentTarget.style.background='var(--hover-surface)'}
                onMouseLeave={e => e.currentTarget.style.background=''}>
                <div style="flex:1;min-width:0">
                  <div style="font-size:15px;font-weight:600;color:var(--text-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{c.title || 'Conversación'}</div>
                  <div style="font-size:12px;color:var(--text-3);margin-top:2px">
                    {(c.messages?.length || 0)} mensajes
                    {c.updatedAt ? ` · ${new Date(c.updatedAt).toLocaleDateString()}` : ''}
                  </div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); toggleFavorite(c.id) }}
                  style={`background:none;border:none;cursor:pointer;font-size:18px;color:${c.favorite?'var(--amber)':'var(--text-3)'};padding:4px`}
                  title={c.favorite?'Quitar de favoritos':'Añadir a favoritos'}>
                  {c.favorite ? '★' : '☆'}
                </button>
                <button onClick={(e) => { e.stopPropagation(); deleteConversation(c.id) }}
                  style="background:none;border:none;cursor:pointer;font-size:16px;color:var(--text-3);padding:4px" title={t('cl.delete')}>×</button>
              </div>
            )}
          </For>
        </div>
      </Show>
    </div>
  )
}
