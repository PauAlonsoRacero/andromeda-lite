/**
 * ContextPanel — RAG local (Pro).
 *
 * Indexa documentos de texto en el índice BM25 local (/api/rag/*) para que el
 * chat los use como contexto y cite las fuentes. Todo ocurre en tu máquina.
 * QoL: arrastrar y soltar archivos, prueba de búsqueda en vivo, borrado por doc.
 */
import { createSignal, createResource, For, Show } from 'solid-js'
import axios from 'axios'
import { t } from '../stores/i18n.js'
import { notifyChange } from '../stores/events.js'

const MAX_KB = 500
const TEXT_EXT = /\.(txt|md|markdown|py|js|jsx|ts|tsx|json|yaml|yml|toml|csv|html|css|sh|ps1|sql|ini|cfg|log)$/i

export default function ContextPanel() {
  const [docs, { refetch }] = createResource(async () => {
    const r = await axios.get('/api/rag/documents')
    return r.data.documents || []
  })
  const [stats, { refetch: refetchStats }] = createResource(async () =>
    (await axios.get('/api/rag/stats')).data)
  const [busy, setBusy] = createSignal(false)
  const [drag, setDrag] = createSignal(false)
  const [msg, setMsg] = createSignal('')
  const [q, setQ] = createSignal('')
  const [hits, setHits] = createSignal(null)

  async function indexFiles(files) {
    setBusy(true); setMsg('')
    let ok = 0, skipped = 0
    for (const f of files) {
      if (!TEXT_EXT.test(f.name) || f.size > MAX_KB * 1024) { skipped++; continue }
      const text = await f.text()
      if (!text.trim()) { skipped++; continue }
      await axios.post('/api/rag/documents', {
        id: f.name, text, meta: { name: f.name, size: f.size },
      })
      ok++
    }
    setBusy(false)
    setMsg(skipped ? t('rag.indexed_some').replace('{ok}', ok).replace('{skip}', skipped)
                   : t('rag.indexed_ok').replace('{ok}', ok))
    refetch(); refetchStats(); notifyChange('rag')
  }

  async function removeDoc(id) {
    await axios.delete(`/api/rag/documents/${encodeURIComponent(id)}`)
    refetch(); refetchStats(); notifyChange('rag')
  }

  async function testQuery() {
    if (!q().trim()) return
    const r = await axios.get('/api/rag/query', { params: { q: q(), k: 3 } })
    setHits(r.data.results || [])
  }

  return (
    <div class="card" style="padding:16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <h3 style="margin:0;font-size:var(--fs-base)">📚 {t('rag.title')}</h3>
        <Show when={stats()}>
          <span style="font-size:var(--fs-xs);color:var(--text-3)">
            {stats().documents} {t('rag.docs')} · {stats().chunks} chunks
          </span>
        </Show>
      </div>
      <p style="font-size:var(--fs-sm);color:var(--text-3);margin:0 0 10px">{t('rag.desc')}</p>

      {/* Zona de subida: click o arrastrar */}
      <label
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); indexFiles([...e.dataTransfer.files]) }}
        style={`display:block;border:1.5px dashed ${drag() ? 'var(--accent)' : 'var(--border)'};
                border-radius:10px;padding:18px;text-align:center;cursor:pointer;
                font-size:var(--fs-sm);color:var(--text-3);transition:border-color .15s`}>
        <input type="file" multiple style="display:none"
               onChange={e => { indexFiles([...e.target.files]); e.target.value = '' }} />
        {busy() ? t('rag.indexing') : t('rag.drop_hint')}
      </label>
      <Show when={msg()}>
        <div style="font-size:var(--fs-xs);color:var(--text-3);margin-top:6px">{msg()}</div>
      </Show>

      {/* Documentos indexados */}
      <Show when={docs()?.length}>
        <div style="margin-top:12px;display:flex;flex-direction:column;gap:4px">
          <For each={docs()}>{d => (
            <div style="display:flex;justify-content:space-between;align-items:center;
                        background:var(--bg-2);border-radius:10px;padding:6px 10px;font-size:var(--fs-sm)">
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                {d.meta?.name || d.id}
                <span style="color:var(--text-3)"> · {d.chunks} chunks</span>
              </span>
              <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:2px 8px"
                      title={t('rag.remove')} onClick={() => removeDoc(d.id)}>✕</button>
            </div>
          )}</For>
        </div>
      </Show>

      {/* Prueba de búsqueda */}
      <div style="display:flex;gap:6px;margin-top:12px">
        <input value={q()} onInput={e => setQ(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && testQuery()}
               placeholder={t('rag.query_ph')}
               style="flex:1;background:var(--bg-2);border:1px solid var(--border);
                      border-radius:10px;padding:7px 10px;font-size:var(--fs-sm);color:var(--text-1)" />
        <button class="btn btn-glass" style="font-size:var(--fs-sm)" onClick={testQuery}>{t('rag.query_btn')}</button>
      </div>
      <Show when={hits() !== null}>
        <div style="margin-top:8px;display:flex;flex-direction:column;gap:6px">
          <Show when={!hits().length}>
            <div style="font-size:var(--fs-xs);color:var(--text-3)">{t('rag.no_hits')}</div>
          </Show>
          <For each={hits()}>{h => (
            <div style="background:var(--bg-2);border-radius:10px;padding:8px 10px;font-size:var(--fs-xs)">
              <div style="color:var(--accent);margin-bottom:3px">[{h.doc_id}] · score {h.score}</div>
              <div style="color:var(--text-2);max-height:60px;overflow:hidden">{h.text}</div>
            </div>
          )}</For>
        </div>
      </Show>
    </div>
  )
}
