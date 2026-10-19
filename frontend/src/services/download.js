/**
 * download.js — Guardar archivos desde la app.
 *
 * En la app de escritorio (pywebview) no existe gestor de descargas: el truco
 * de crear un blob y hacer click en un <a download> hace que la ventana NAVEGUE
 * al contenido, dejando al usuario atrapado en una página de texto sin vuelta
 * atrás. Por eso se pide al backend que escriba el archivo en Descargas.
 *
 * En un navegador normal (modo web / Docker) se usa la descarga clásica.
 */
import axios from 'axios'

/** True si estamos dentro de la ventana de escritorio de Andromeda. */
export function isDesktopApp() {
  return typeof window !== 'undefined' && (
    !!window.pywebview ||
    /pywebview/i.test(navigator.userAgent || '')
  )
}

/**
 * Guarda contenido de texto como archivo.
 * @returns {Promise<{ok: boolean, path?: string, error?: string}>}
 */
export async function saveTextFile(filename, content, mime = 'text/plain;charset=utf-8') {
  // Camino de escritorio: el backend escribe en Descargas y devuelve la ruta.
  try {
    const r = await axios.post('/api/save-file', { filename, content })
    if (r.data?.saved) return { ok: true, path: r.data.path, name: r.data.name }
  } catch (e) {
    // Si el endpoint no está disponible, se intenta el método del navegador.
    if (isDesktopApp()) {
      return { ok: false, error: e?.response?.data?.error || e.message }
    }
  }

  // Camino navegador.
  try {
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

/** Igual que saveTextFile pero para contenido binario ya obtenido como Blob. */
export async function saveBlobFile(filename, blob) {
  if (isDesktopApp()) {
    // Los documentos binarios (docx, pdf) los genera el backend; si llegamos
    // aquí con un blob en escritorio, se convierte a texto solo si es texto.
    if (blob.type.startsWith('text/') || blob.type.includes('json')) {
      return saveTextFile(filename, await blob.text(), blob.type)
    }
  }
  try {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

/**
 * Descarga un archivo de la carpeta de trabajo (o de un proyecto).
 * En escritorio lo copia el backend a Descargas: allí los enlaces de descarga
 * no hacen nada, y los botones "Descargar" no funcionaban con Word o PDF.
 */
export async function downloadWorkspaceFile(path, projectId = null) {
  if (isDesktopApp()) {
    try {
      const r = await fetch('/api/files/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, project_id: projectId }),
      })
      const d = await r.json()
      return r.ok ? { ok: true, saved: d.saved, name: d.name } : { ok: false, error: d.error_key }
    } catch (e) { return { ok: false, error: e.message } }
  }
  const url = projectId
    ? `/api/projects/${encodeURIComponent(projectId)}/files/raw?path=${encodeURIComponent(path)}`
    : `/api/files/raw?path=${encodeURIComponent(path)}&download=1`
  const a = document.createElement('a')
  a.href = url; a.download = path.split('/').pop()
  document.body.appendChild(a); a.click(); document.body.removeChild(a)
  return { ok: true }
}
