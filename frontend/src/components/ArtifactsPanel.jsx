/**
 * ArtifactsPanel.jsx — Artefactos = lo que la IA ha creado para ti en el
 * workspace (Escritorio/Andromeda): páginas web, documentos, hojas, imágenes.
 *
 * A diferencia de un explorador de archivos, aquí los artefactos se PREVISUALIZAN:
 * un HTML se ve renderizado en un iframe (no su código), las imágenes se ven,
 * el markdown/texto se lee con formato. Es el equivalente local a los artefactos
 * de Claude. Se leen del backend (en la app de escritorio localStorage no es fiable).
 */
import { createSignal, createResource, For, Show } from 'solid-js'
import { t } from '../stores/i18n.js'

const ICON_BY_EXT = {
  html: '🌐', htm: '🌐', txt: '📄', md: '📝',
  docx: '📘', pdf: '📕', xlsx: '📊',
  css: '🎨', js: '⚙', json: '◆', py: '🐍',
  csv: '📊', png: '🖼', jpg: '🖼', jpeg: '🖼', svg: '🖼', webp: '🖼', gif: '🖼',
}
const IMG_EXTS  = ['png', 'jpg', 'jpeg', 'svg', 'webp', 'gif']
const TEXT_EXTS = ['txt', 'md', 'html', 'htm', 'css', 'js', 'json', 'py', 'csv', 'xml', 'yaml', 'yml']

function extOf(name) {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}
function fmtSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
function fmtDate(mtime) {
  if (!mtime) return ''
  try { return new Date(mtime * 1000).toLocaleString() } catch { return '' }
}
function rawUrl(path, download) {
  return `/api/files/raw?path=${encodeURIComponent(path)}${download ? '&download=1' : ''}`
}

async function fetchArtifacts() {
  const r = await fetch('/api/files/list')
  if (!r.ok) return []
  const data = await r.json()
  return (data.files || [])
    .filter(f => !f.is_dir)
    .sort((a, b) => (b.modified || 0) - (a.modified || 0))
}

export default function ArtifactsPanel() {
  const [artifacts, { refetch }] = createResource(fetchArtifacts)
  const [preview, setPreview] = createSignal(null)  // {path, ext, content?}

  async function open(file) {
    const ext = extOf(file.path)
    // HTML e imágenes se sirven directos vía /raw (render real). Para el resto
    // de texto cargamos el contenido para mostrarlo con formato.
    if (ext === 'html' || ext === 'htm' || IMG_EXTS.includes(ext)) {
      setPreview({ path: file.path, ext })
      return
    }
    if (TEXT_EXTS.includes(ext)) {
      try {
        const r = await fetch(`/api/files/read?path=${encodeURIComponent(file.path)}`)
        const data = await r.json()
        setPreview({ path: file.path, ext, content: data.content || '' })
      } catch { /* noop */ }
      return
    }
    // Binarios (docx/xlsx/pdf): abrir/descargar
    window.open(rawUrl(file.path, false), '_blank')
  }

  async function remove(file, ev) {
    ev.stopPropagation()
    if (!confirm(t('art.confirm_delete').replace('{f}', file.path))) return
    try {
      await fetch('/api/files/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: file.path }),
      })
      refetch()
    } catch { /* noop */ }
  }

  function download(file, ev) {
    ev.stopPropagation()
    window.open(rawUrl(file.path, true), '_blank')
  }

  return (
    <div class="panel-page" style="max-width:900px">
      <div class="panel-page-header">
        <div>
          <div class="panel-page-title">{t('art.title')}</div>
          <div class="panel-page-sub">{t('art.subtitle')}</div>
        </div>
        <button class="btn btn-ghost" onClick={() => refetch()} title={t('art.refresh')}>↻</button>
      </div>

      <Show when={!artifacts.loading} fallback={
        <div class="card" style="text-align:center;padding:48px">
          <div class="spin" style="width:22px;height:22px;margin:0 auto" />
        </div>
      }>
        <Show when={(artifacts() || []).length > 0} fallback={
          <div class="card" style="text-align:center;padding:48px">
            <div style="font-size:40px;opacity:0.2;margin-bottom:16px">⬡</div>
            <div style="font-size:16px;font-weight:600;margin-bottom:8px">{t('art.empty')}</div>
            <div style="font-size:13px;color:var(--text-3);max-width:440px;margin:0 auto;line-height:1.6">
              {t('art.empty_hint')}
            </div>
          </div>
        }>
          <div class="stagger" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
            <For each={artifacts()}>
              {(a) => (
                <div class="card" style="margin-bottom:0;cursor:pointer;position:relative" onClick={() => open(a)}>
                  {/* Miniatura: imágenes muestran preview real */}
                  <Show when={IMG_EXTS.includes(extOf(a.path))} fallback={
                    <div class="app-icon" style="width:42px;height:42px;font-size:20px;margin-bottom:12px">
                      {ICON_BY_EXT[extOf(a.path)] || '📄'}
                    </div>
                  }>
                    <img src={rawUrl(a.path, false)} alt={a.path}
                         style="width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:12px;background:var(--surface-1)" />
                  </Show>
                  <div style="font-size:15px;font-weight:600;margin-bottom:4px;word-break:break-all">{a.path}</div>
                  <div style="font-size:12px;color:var(--text-3)">
                    {fmtSize(a.size)}{a.size ? ' · ' : ''}{fmtDate(a.modified)}
                  </div>
                  <div style="display:flex;gap:6px;margin-top:10px">
                    <button class="btn btn-ghost" style="font-size:11px;padding:4px 10px"
                            onClick={(e) => download(a, e)} title={t('art.download')}>⬇ {t('art.download')}</button>
                    <button class="btn btn-ghost" style="font-size:11px;padding:4px 10px;color:var(--red)"
                            onClick={(e) => remove(a, e)} title={t('art.delete')}>🗑</button>
                  </div>
                </div>
              )}
            </For>
          </div>
        </Show>
      </Show>

      {/* Previsualización */}
      <Show when={preview()}>
        <div onClick={() => setPreview(null)}
             style="position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;
                    align-items:center;justify-content:center;z-index:1000;padding:24px">
          <div onClick={(e) => e.stopPropagation()}
               style="background:var(--bg-1);border:1px solid var(--border);border-radius:14px;
                      max-width:900px;width:100%;max-height:86vh;display:flex;flex-direction:column;overflow:hidden">
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:14px 18px;border-bottom:1px solid var(--border)">
              <div style="font-weight:600">{preview().path}</div>
              <div style="display:flex;gap:8px;align-items:center">
                <button class="btn btn-ghost" style="font-size:12px" onClick={() => window.open(rawUrl(preview().path, true), '_blank')}>⬇ {t('art.download')}</button>
                <button class="btn btn-ghost" onClick={() => setPreview(null)}>✕</button>
              </div>
            </div>

            {/* HTML → iframe renderizado */}
            <Show when={preview().ext === 'html' || preview().ext === 'htm'}>
              <iframe src={rawUrl(preview().path, false)} title="preview"
                      sandbox="allow-scripts allow-same-origin"
                      style="width:100%;height:70vh;border:0;background:#fff" />
            </Show>

            {/* Imagen */}
            <Show when={IMG_EXTS.includes(preview().ext)}>
              <div style="padding:18px;overflow:auto;display:flex;justify-content:center;background:var(--surface-1)">
                <img src={rawUrl(preview().path, false)} alt={preview().path}
                     style="max-width:100%;max-height:70vh;object-fit:contain" />
              </div>
            </Show>

            {/* Texto / código */}
            <Show when={preview().content != null}>
              <pre style="margin:0;padding:18px;overflow:auto;font-size:13px;line-height:1.5;
                          white-space:pre-wrap;word-break:break-word">{preview().content}</pre>
            </Show>
          </div>
        </div>
      </Show>
    </div>
  )
}
