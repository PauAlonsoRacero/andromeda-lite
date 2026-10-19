/** Controles compartidos de los ajustes (interruptor y fila con descripción). */

export function Toggle(props) {
  return (
    <button
      onClick={() => props.onChange(!props.checked)}
      style={{
        width: '46px', height: '28px', 'border-radius': '14px', border: 'none',
        cursor: 'pointer', position: 'relative', transition: 'all 0.2s', 'flex-shrink': 0,
        background: props.checked ? 'var(--green)' : 'var(--toggle-off)',
      }}
    >
      <span style={{
        position: 'absolute', top: '3px', left: props.checked ? '21px' : '3px',
        width: '22px', height: '22px', 'border-radius': '50%', background: 'white',
        transition: 'all 0.2s', 'box-shadow': '0 1px 3px rgba(0,0,0,0.3)',
      }} />
    </button>
  )
}

export function SettingRow(props) {
  return (
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:16px 0;border-bottom:1px solid var(--glass-border)">
      <div style="flex:1">
        <div style="font-size:var(--fs-base);font-weight:600;color:var(--text-1);margin-bottom:3px">{props.title}</div>
        <div style="font-size:var(--fs-sm);color:var(--text-3);line-height:1.5">{props.desc}</div>
      </div>
      <div style="flex-shrink:0;padding-top:2px">{props.children}</div>
    </div>
  )
}
