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
import { openPreview } from '../stores/preview.js'
import { downloadWorkspaceFile } from '../services/download.js'
import { t } from '../stores/i18n.js'

const ICON_BY_EXT = {
  html: '🌐', htm: '🌐', txt: '📄', md: '📝',
  docx: '📘', pdf: '📕', xlsx: '📊',
  css: '🎨', js: '⚙', json: '◆', py: '🐍',
  csv: '📊', png: '🖼', jpg: '🖼', jpeg: '🖼', svg: '🖼', webp: '🖼', gif: '🖼',
}
const IMG_EXTS  = ['png', 'jpg', 'jpeg', 'svg', 'webp', 'gif']
const TEXT_EXTS = ['txt', 'md', 'html', 'htm', 'css', 'js', 'jsx', 'ts', 'tsx', 'json', 'py', 'csv', 'xml',
  'yaml', 'yml', 'toml', 'ini', 'sh', 'sql', 'java', 'c', 'cpp', 'h', 'go', 'rs', 'php', 'rb', 'log']

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
  // `v` evita la caché del navegador: sin él se veía la primera versión del
  // archivo aunque se hubiera modificado después.
  return `/api/files/raw?path=${encodeURIComponent(path)}${download ? '&download=1' : ''}&v=${Date.now()}`
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



  // Abre el archivo en el panel lateral compartido con el chat. Antes se usaba
  // un modal propio que mostraba el HTML en blanco (X-Frame-Options: DENY) y
  // enviaba Word y Excel a una ventana nueva, que en escritorio no hace nada.
  function open(file) { openPreview(file.path) }


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

  const [aviso, setAviso] = createSignal('')
  async function download(file, ev) {
    ev.stopPropagation()
    const r = await downloadWorkspaceFile(file.path)
    if (r.saved) { setAviso(`${t('dl.saved_to')} ${r.saved}`); setTimeout(() => setAviso(''), 3500) }
  }

  return (
    <div class="panel-page" style="max-width:900px">
      <Show when={aviso()}><div class="dl-toast" role="status">✓ {aviso()}</div></Show>
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
            <div style="font-size:var(--fs-md);font-weight:600;margin-bottom:8px">{t('art.empty')}</div>
            <div style="font-size:var(--fs-base);color:var(--text-3);max-width:440px;margin:0 auto;line-height:1.6">
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
                    <div class="app-icon" style="width:42px;height:42px;font-size:var(--fs-lg);margin-bottom:12px">
                      {ICON_BY_EXT[extOf(a.path)] || '📄'}
                    </div>
                  }>
                    <img src={rawUrl(a.path, false)} alt={a.path}
                         style="width:100%;height:120px;object-fit:cover;border-radius:10px;margin-bottom:12px;background:var(--surface-1)" />
                  </Show>
                  <div style="font-size:var(--fs-md);font-weight:600;margin-bottom:4px;word-break:break-all">{a.path}</div>
                  <div style="font-size:var(--fs-sm);color:var(--text-3)">
                    {fmtSize(a.size)}{a.size ? ' · ' : ''}{fmtDate(a.modified)}
                  </div>
                  <div style="display:flex;gap:6px;margin-top:10px">
                    <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:4px 10px"
                            onClick={(e) => download(a, e)} title={t('art.download')}>⬇ {t('art.download')}</button>
                    <button class="btn btn-ghost" style="font-size:var(--fs-xs);padding:4px 10px;color:var(--red)"
                            onClick={(e) => remove(a, e)} title={t('art.delete')}>🗑</button>
                  </div>
                </div>
              )}
            </For>
          </div>
        </Show>
      </Show>

      {/* Previsualización */}
    </div>
  )
}
