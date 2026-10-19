/**
 * preview.js — Archivo abierto en el panel lateral de vista previa.
 *
 * Lo comparten el chat (al pulsar un archivo creado) y Artefactos, como el
 * panel de la derecha de Claude.
 */
import { createSignal } from 'solid-js'

export const [previewFile, setPreviewFile] = createSignal(null)   // { path, projectId? }

export function openPreview(path, projectId = null) {
  if (path) setPreviewFile({ path, projectId, t: Date.now() })
}
export function closePreview() { setPreviewFile(null) }
