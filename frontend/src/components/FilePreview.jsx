/**
 * FilePreview.jsx — Panel lateral de vista previa (como el de Claude).
 *
 * Páginas web, imágenes, PDF, Word, Excel y CSV se ven renderizados; el resto
 * de texto, con su contenido. Las páginas web se sirven por su ruta real
 * (/api/files/view/…) para que sus CSS, JS e imágenes relativos funcionen, y
 * el servidor las aísla (CSP sandbox) para que no puedan tocar la app.
 */
import { createSignal, createEffect, Show, onCleanup } from 'solid-js'
import { Portal } from 'solid-js/web'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { previewFile, closePreview } from '../stores/preview.js'
import { t } from '../stores/i18n.js'
import { downloadWorkspaceFile } from '../services/download.js'

const VISUAL = ['html', 'htm', 'svg', 'pdf', 'docx', 'xlsx', 'csv']
const IMAGEN = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']

const ext = (p) => (p || '').split('.').pop().toLowerCase()
const viewUrl = (f) => {
  const ruta = (f.path || '').split('/').map(encodeURIComponent).join('/')
  const base = f.projectId ? `/api/projects/${encodeURIComponent(f.projectId)}/view` : '/api/files/view'
  return `${base}/${ruta}?v=${f.t || Date.now()}`
}

export default function FilePreview() {
  const [codigo, setCodigo] = createSignal(null)     // texto si se ve como código
  const [cerrando, setCerrando] = createSignal(false)
  const [error, setError] = createSignal('')
  const [aviso, setAviso] = createSignal('')

  const cargarTexto = async (f) => {
    try {
      const r = await fetch(viewUrl(f))
      if (!r.ok) throw new Error(String(r.status))
      setCodigo(await r.text())
    } catch { setError(t('prev.load_error')) }
  }

  createEffect(() => {
    const f = previewFile()
    setCodigo(null); setError(''); setCerrando(false)
    if (f && !VISUAL.includes(ext(f.path)) && !IMAGEN.includes(ext(f.path))) cargarTexto(f)
  })

  const cerrar = () => { setCerrando(true); setTimeout(closePreview, 180) }
  const alTeclado = (e) => { if (e.key === 'Escape' && previewFile()) cerrar() }
  document.addEventListener('keydown', alTeclado)
  onCleanup(() => document.removeEventListener('keydown', alTeclado))

  return (
    <Show when={previewFile()}>
      {(f) => (
        // Portal: se pinta directamente en <body>. Un position:fixed dentro de
        // un contenedor con transform o backdrop-filter queda recortado por él.
        <Portal>
          <div class={`preview-backdrop ${cerrando() ? 'out' : ''}`} onClick={cerrar} />
          <aside class={`preview-panel ${cerrando() ? 'out' : ''}`} role="dialog" aria-label={f().path}>
            <header class="preview-head">
              <div class="preview-title" title={f().path}>{f().path.split('/').pop()}</div>
              <Show when={['html', 'htm', 'svg'].includes(ext(f().path))}>
                <button class="btn btn-ghost preview-btn"
                        onClick={() => codigo() == null ? cargarTexto(f()) : setCodigo(null)}>
                  {codigo() == null ? t('art.view_code') : t('art.view_page')}
                </button>
              </Show>
              <button class="btn btn-ghost preview-btn" aria-label={t('art.download')}
                      onClick={async () => {
                        const r = await downloadWorkspaceFile(f().path, f().projectId)
                        if (r.saved) { setAviso(`${t('dl.saved_to')} ${r.saved}`); setTimeout(() => setAviso(''), 3500) }
                      }}>⬇</button>
              <button class="btn btn-ghost preview-btn" onClick={cerrar} aria-label={t('prev.close')}>✕</button>
            </header>
            <Show when={aviso()}><div class="dl-toast" role="status">✓ {aviso()}</div></Show>
            <div class="preview-body">
              <Show when={error()}><div class="preview-empty">{error()}</div></Show>
              <Show when={IMAGEN.includes(ext(f().path))}>
                <div class="preview-img"><img src={viewUrl(f())} alt={f().path} /></div>
              </Show>
              <Show when={VISUAL.includes(ext(f().path)) && codigo() == null}>
                <iframe class="preview-frame" src={viewUrl(f())} title={f().path} />
              </Show>
              <Show when={codigo() != null && ext(f().path) === 'md'}>
                <div class="preview-md" innerHTML={DOMPurify.sanitize(marked.parse(codigo()))} />
              </Show>
              <Show when={codigo() != null && ext(f().path) !== 'md'}>
                <pre class="preview-code">{codigo()}</pre>
              </Show>
            </div>
          </aside>
        </Portal>
      )}
    </Show>
  )
}
