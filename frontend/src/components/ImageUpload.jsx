/**
 * ImageUpload.jsx — Componente de upload de imágenes para el chat.
 * Permite arrastrar, pegar desde portapapeles o seleccionar imágenes.
 * Las convierte a base64 para enviarlas al backend.
 */
import { createSignal, For, Show } from 'solid-js'
import { t } from '../stores/i18n.js'

export default function ImageUpload({ onImages, maxImages = 4 }) {
  const [images, setImages] = createSignal([])
  const [dragging, setDragging] = createSignal(false)
  let inputRef

  function processFile(file) {
    if (!file.type.startsWith('image/')) return
    const reader = new FileReader()
    reader.onload = (e) => {
      const b64 = e.target.result  // data:image/...;base64,...
      const newImages = [...images(), { src: b64, name: file.name }].slice(0, maxImages)
      setImages(newImages)
      onImages(newImages.map(i => i.src))
    }
    reader.readAsDataURL(file)
  }

  function handleFiles(files) {
    Array.from(files).forEach(processFile)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  function handlePaste(e) {
    const items = e.clipboardData?.items
    if (!items) return
    Array.from(items).forEach(item => {
      if (item.type.startsWith('image/')) {
        processFile(item.getAsFile())
      }
    })
  }

  function removeImage(idx) {
    const updated = images().filter((_, i) => i !== idx)
    setImages(updated)
    onImages(updated.map(i => i.src))
  }

  // Listen for paste globally when there are no images
  function handleGlobalPaste(e) {
    handlePaste(e)
  }

  return (
    <div>
      {/* Preview de imágenes */}
      <Show when={images().length > 0}>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
          <For each={images()}>
            {(img, idx) => (
              <div class="img-preview-wrap">
                <img src={img.src} class="img-preview" alt={img.name} />
                <button class="img-preview-del" onClick={() => removeImage(idx())}>✕</button>
              </div>
            )}
          </For>
        </div>
      </Show>

      {/* Drop zone */}
      <Show when={images().length < maxImages}>
        <div
          class={`img-drop-zone ${dragging() ? 'drag-over' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onPaste={handlePaste}
          onClick={() => inputRef.click()}
          title={t('img.hint')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-4.5-4.5L5 21"/></svg>
          <span>
            {dragging()
              ? 'Suelta aquí...'
              : `Añadir imagen (arrastra, pega o clic) · ${images().length}/${maxImages}`}
          </span>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          style="display:none"
          onChange={e => handleFiles(e.target.files)}
        />
      </Show>
    </div>
  )
}
