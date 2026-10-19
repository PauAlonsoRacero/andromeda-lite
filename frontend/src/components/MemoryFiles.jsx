/**
 * MemoryFiles.jsx — La memoria organizada como en Claude.
 *
 * Arriba, los cuatro ajustes (buscar en conversaciones, generar memoria, temas
 * sensibles e importar de otro asistente). Debajo, lo que Andromeda recuerda,
 * agrupado en secciones (Tú, Temas, Áreas, Personas, Notas): cada "archivo" con
 * su resumen, su última actualización y acciones para ver, editar o borrar.
 */
import { createSignal, createResource, For, Show } from 'solid-js'
import axios from 'axios'
import { t, lang } from '../stores/i18n.js'
import * as S from '../stores/settings.js'
import { Toggle, SettingRow } from './SettingControls.jsx'

const fecha = (ts) => {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  const dias = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (dias < 1) return t('memf.today')
  if (dias < 7) return t('memf.days_ago').replace('{n}', dias)
  return d.toLocaleDateString(lang(), { day: 'numeric', month: 'short' })
}

export default function MemoryFiles() {
  const [datos, { refetch }] = createResource(async () => (await axios.get('/api/memory/files')).data)
  const [texto, setTexto] = createSignal('')
  const [aviso, setAviso] = createSignal('')
  const [importar, setImportar] = createSignal(false)
  const [promptImp, setPromptImp] = createSignal('')
  const [pegado, setPegado] = createSignal('')

  const avisar = (m) => { setAviso(m); setTimeout(() => setAviso(''), 4000) }

  async function cambiarSensibles(v) {
    S.setMemSensitive(v)
    if (!v) {
      // Apagar = eliminar lo ya guardado. Si algo falla se avisa, como en Claude.
      try {
        const r = (await axios.post('/api/memory/purge-sensitive')).data
        avisar(r.failed ? t('memf.purge_incomplete') : t('memf.purged').replace('{n}', r.deleted))
        refetch()
      } catch { avisar(t('memf.purge_incomplete')) }
    }
  }

  async function abrirImportar() {
    setImportar(v => !v)
    if (!promptImp()) {
      try { setPromptImp((await axios.get('/api/memory/import-prompt')).data.prompt) } catch { /* opcional */ }
    }
  }

  async function hacerImportar() {
    try {
      const r = (await axios.post('/api/memory/import', { text: pegado() })).data
      avisar(t('memf.imported').replace('{n}', r.imported))
      setPegado(''); setImportar(false); refetch()
    } catch { avisar(t('err.generic')) }
  }



  async function borrarArchivo(sec, id) {
    if (!confirm(t('memf.confirm_delete'))) return
    await axios.delete('/api/memory/profile/file', { params: { section: sec, file: id } }); refetch()
  }

  const nombre = (sec, f) => f.name || t(`memf.file_${f.id}`)
  // Descripción del tema (como en Claude), no la lista de datos
  const descripcion = (f) => f.id.startsWith('persona:')
    ? t('memf.desc_persona').replace('{name}', f.name || '')
    : t(`memf.desc_${f.id}`)

  const [tema, setTema] = createSignal(null)       // { sec, f, lineas, editar, manual }
  const [cambio, setCambio] = createSignal('')
  const [trabajando, setTrabajando] = createSignal(false)
  const abrirTema = (sec, f, editar) => {
    setCambio('')
    setTema({ sec, f, lineas: f.facts.map(x => x.text), editar, manual: false })
  }
  async function aplicarIA() {
    const tm = tema()
    setTrabajando(true)
    try {
      const r = (await axios.post('/api/memory/profile/file/ai-edit', {
        section: tm.sec, file: tm.f.id, name: nombre(tm.sec, tm.f), instruction: cambio(),
      })).data
      setTema({ ...tm, lineas: r.lines, editar: false }); setCambio(''); refetch()
    } catch (e) { avisar(t(e?.response?.data?.error_key || 'err.generic')) }
    setTrabajando(false)
  }
  async function guardarTexto() {
    const tm = tema()
    await axios.post('/api/memory/profile/file/rewrite', { section: tm.sec, file: tm.f.id, text: texto() })
    setTema(null); refetch()
  }

  return (
    <div class="memf">
      {/* ── Ajustes ─────────────────────────────────────────────────────── */}
      <SettingRow title={t('memf.search_title')} desc={t('memf.search_desc')}>
        <Toggle checked={S.memConversationSearch()} onChange={S.setMemConversationSearch} />
      </SettingRow>
      <SettingRow title={t('memf.gen_title')} desc={t('memf.gen_desc')}>
        <Toggle checked={S.memAutogenerate()} onChange={S.setMemAutogenerate} />
      </SettingRow>
      <SettingRow title={t('memf.sens_title')} desc={t('memf.sens_desc')}>
        <Toggle checked={S.memSensitive()} onChange={cambiarSensibles} />
      </SettingRow>
      <SettingRow title={t('memf.imp_title')} desc={t('memf.imp_desc')}>
        <button class="btn btn-glass" style="font-size:var(--fs-sm)" onClick={abrirImportar}>
          {importar() ? t('prev.close') : t('memf.imp_start')}
        </button>
      </SettingRow>
      <Show when={importar()}>
        <div class="memf-import">
          <div class="memf-step">1. {t('memf.imp_step1')}</div>
          <pre class="memf-prompt">{promptImp()}</pre>
          <button class="btn btn-ghost" style="font-size:var(--fs-xs)"
                  onClick={() => navigator.clipboard?.writeText(promptImp()).then(() => avisar(t('dg.copied')))}>
            ⎘ {t('dg.copy')}
          </button>
          <div class="memf-step">2. {t('memf.imp_step2')}</div>
          <textarea class="g-input" rows="6" value={pegado()} onInput={e => setPegado(e.currentTarget.value)}
                    placeholder={t('memf.imp_placeholder')} style="width:100%;resize:vertical" />
          <button class="btn btn-primary" style="margin-top:8px" disabled={!pegado().trim()} onClick={hacerImportar}>
            {t('memf.imp_do')}
          </button>
        </div>
      </Show>
      <Show when={aviso()}><div class="dl-toast" role="status">{aviso()}</div></Show>

      {/* ── Lo que Andromeda recuerda, por temas (como en Claude) ─────────── */}
      <Show when={datos()}>
        <For each={datos().sections.filter(s => s.files.length)}>
          {(sec) => (
            <div class="memf-section">
              <div class="memf-section-title">{t(`memf.sec_${sec.id}`)}</div>
              <div class="memf-list">
                <For each={sec.files}>
                  {(f) => (
                    <div class="memf-item" role="button" tabindex="0"
                         onClick={() => abrirTema(sec.id, f, false)}
                         onKeyDown={e => e.key === 'Enter' && abrirTema(sec.id, f, false)}>
                      <span class="memf-item-name">{nombre(sec.id, f)}</span>
                      <span class="memf-item-desc">{descripcion(f)}</span>
                      <span class="memf-item-date">{t('memf.updated')} {fecha(f.updated)}</span>
                      <span class="memf-item-actions" onClick={e => e.stopPropagation()}>
                        <button class="memf-icon" aria-label={t('memf.edit')} title={t('memf.edit')}
                                onClick={() => abrirTema(sec.id, f, true)}>
                          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
                        </button>
                        <button class="memf-icon" aria-label={t('art.delete')} title={t('art.delete')}
                                onClick={() => borrarArchivo(sec.id, f.id)}>
                          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/></svg>
                        </button>
                      </span>
                    </div>
                  )}
                </For>
              </div>
            </div>
          )}
        </For>
        <Show when={!datos().sections.some(s => s.files.length)}>
          <div class="memf-empty" style="margin-top:22px">{t('memf.empty_all')}</div>
        </Show>
      </Show>

      {/* ── Tema abierto: ver, describir un cambio o editar a mano ────────── */}
      <Show when={tema()}>
        <div class="memf-modal-bg" onClick={() => setTema(null)}>
          <div class="memf-modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
            <div class="memf-modal-head">
              <div>
                <div class="memf-modal-title">{nombre(tema().sec, tema().f)}</div>
                <div class="memf-modal-desc">{descripcion(tema().f)}</div>
              </div>
              <button class="memf-icon" onClick={() => setTema(null)} aria-label={t('prev.close')}>✕</button>
            </div>
            <Show when={!tema().manual} fallback={
              <textarea class="g-input memf-textarea" rows="10" value={texto()}
                        onInput={e => setTexto(e.currentTarget.value)} />
            }>
              <ul class="memf-content">
                <For each={tema().lineas}>{(l) => <li>{l}</li>}</For>
              </ul>
            </Show>
            <Show when={tema().editar}>
              <div class="memf-prompt-bar">
                <input class="memf-prompt-input" placeholder={t('memf.describe_change')} value={cambio()}
                       onInput={e => setCambio(e.currentTarget.value)}
                       onKeyDown={e => e.key === 'Enter' && cambio().trim() && aplicarIA()}
                       disabled={trabajando()} />
                <button class="btn btn-primary" disabled={!cambio().trim() || trabajando()} onClick={aplicarIA}>
                  {trabajando() ? '…' : t('memf.apply')}
                </button>
              </div>
            </Show>
            <div class="memf-modal-foot">
              <Show when={!tema().editar}>
                <button class="btn btn-glass" onClick={() => setTema({ ...tema(), editar: true })}>{t('memf.edit')}</button>
              </Show>
              <Show when={tema().editar && !tema().manual}>
                <button class="btn btn-ghost" onClick={() => { setTexto(tema().lineas.join('\n')); setTema({ ...tema(), manual: true }) }}>
                  {t('memf.edit_text')}
                </button>
              </Show>
              <Show when={tema().manual}>
                <button class="btn btn-primary" onClick={guardarTexto}>{t('memf.save')}</button>
              </Show>
            </div>
          </div>
        </div>
      </Show>
    </div>
  )
}
