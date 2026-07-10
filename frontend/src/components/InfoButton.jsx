/**
 * InfoButton.jsx — Botón (i) que abre un panel de instrucciones de uso.
 *
 * Estilo Andromeda: icono discreto que, al pulsarlo, despliega un popover con
 * la explicación punto por punto de la sección. Reutilizable en toda la app.
 *
 * Uso:
 *   <InfoButton title="Analíticas" items={[
 *     { h: 'Tasa de éxito', d: 'Porcentaje de peticiones que terminaron bien.' },
 *     ...
 *   ]} />
 */
import { createSignal, For, Show, onCleanup } from 'solid-js'

export default function InfoButton(props) {
  const [open, setOpen] = createSignal(false)

  function toggle(e) {
    e?.stopPropagation()
    setOpen(v => !v)
  }
  function close() { setOpen(false) }

  // Cerrar con Escape.
  const onKey = (e) => { if (e.key === 'Escape') close() }
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onKey)
    onCleanup(() => window.removeEventListener('keydown', onKey))
  }

  return (
    <>
      <button
        onClick={toggle}
        title={props.label || 'Cómo se usa'}
        aria-label="info"
        style={`display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;border:1px solid var(--glass-border);background:${open() ? 'var(--glass-bright)' : 'transparent'};color:${open() ? 'var(--text-1)' : 'var(--text-3)'};cursor:pointer;font-size:12px;font-weight:700;font-style:italic;font-family:Georgia,serif;flex-shrink:0;transition:all .15s;line-height:1`}
      >i</button>

      <Show when={open()}>
        {/* Overlay */}
        <div onClick={close}
          style="position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.45);backdrop-filter:blur(3px);animation:overlayFadeIn .18s ease"
        />
        {/* Panel */}
        <div
          style="position:fixed;z-index:301;top:50%;left:50%;transform:translate(-50%,-50%);width:min(560px,92vw);max-height:80vh;overflow-y:auto;background:var(--glass-bright,rgba(16,18,28,.98));border:1px solid var(--glass-border);border-radius:18px;box-shadow:0 20px 60px rgba(0,0,0,.5);backdrop-filter:blur(24px);padding:24px;animation:modalPopIn .2s cubic-bezier(0.34,1.4,0.5,1)"
        >
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <h3 style="font-size:18px;font-weight:700;color:var(--text-1);margin:0">{props.title}</h3>
            <button onClick={close}
              style="width:28px;height:28px;border-radius:50%;border:1px solid var(--glass-border);background:transparent;color:var(--text-3);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">×</button>
          </div>
          <Show when={props.intro}>
            <p style="font-size:13px;color:var(--text-2);line-height:1.6;margin:0 0 16px">{props.intro}</p>
          </Show>
          <div style="display:flex;flex-direction:column;gap:14px">
            <For each={props.items || []}>
              {(it, i) => (
                <div style="display:flex;gap:12px">
                  <div style="flex-shrink:0;width:24px;height:24px;border-radius:50%;background:var(--accent-soft,rgba(91,120,245,.15));color:var(--blue);font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center">{i() + 1}</div>
                  <div style="min-width:0">
                    <div style="font-size:13.5px;font-weight:600;color:var(--text-1);margin-bottom:2px">{it.h}</div>
                    <div style="font-size:13px;color:var(--text-3);line-height:1.55">{it.d}</div>
                  </div>
                </div>
              )}
            </For>
          </div>
          <Show when={props.tip}>
            <div style="margin-top:18px;padding:11px 13px;border-radius:10px;background:var(--accent-soft,rgba(91,120,245,.1));border:1px solid color-mix(in srgb, var(--blue) 25%, transparent);font-size:12.5px;color:var(--text-2);line-height:1.5">
              💡 {props.tip}
            </div>
          </Show>
        </div>
      </Show>
    </>
  )
}
