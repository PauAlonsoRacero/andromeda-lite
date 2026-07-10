/**
 * ProjectsPanel.jsx — Proyectos funcionales estilo Claude.
 * Crear, entrar, añadir instrucciones de contexto, ver conversaciones, eliminar.
 */
import { createSignal, For, Show } from 'solid-js'
import { conversations, loadConversation } from '../stores/chat.js'
import { t } from '../stores/i18n.js'

const IconFolder = () => <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
const IconClock = () => <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;margin-right:6px"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>
const IconMemory = () => <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px;margin-right:6px"><path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-3 3 3 3 0 0 0 1 5.83V18a3 3 0 0 0 5 2 3 3 0 0 0 5-2v-3.17A3 3 0 0 0 18 9a3 3 0 0 0-3-3 3 3 0 0 0-6 0z"/></svg>

function load() {
  try { return JSON.parse(localStorage.getItem('andromeda_projects') || '[]') }
  catch { return [] }
}
function persist(list) {
  try { localStorage.setItem('andromeda_projects', JSON.stringify(list)) } catch {}
}

export default function ProjectsPanel(props) {
  const [projects, setProjects] = createSignal(load())
  const [creating, setCreating] = createSignal(false)
  const [name, setName] = createSignal('')
  const [openId, setOpenId] = createSignal(null)   // proyecto abierto
  const [instructions, setInstructions] = createSignal('')
  const [schedEnabled, setSchedEnabled] = createSignal(false)
  const [schedDate, setSchedDate] = createSignal('')
  const [schedTime, setSchedTime] = createSignal('')
  const [schedConditions, setSchedConditions] = createSignal('')
  const [memory, setMemory] = createSignal('')

  function save(list) { setProjects(list); persist(list) }

  function create() {
    if (!name().trim()) return
    const proj = { id: crypto.randomUUID(), name: name().trim(), instructions: '',
                   schedule: { enabled: false, date: '', time: '', conditions: '' },
                   memory: '',
                   createdAt: new Date().toISOString(), conversationIds: [] }
    save([proj, ...projects()])
    setName(''); setCreating(false)
    setOpenId(proj.id)   // entrar directamente al crear
  }
  function remove(id) {
    save(projects().filter(p => p.id !== id))
    if (openId() === id) setOpenId(null)
  }
  function openProject(p) {
    setOpenId(p.id)
    setInstructions(p.instructions || '')
    setSchedDate(p.schedule?.date || '')
    setSchedTime(p.schedule?.time || '')
    setSchedConditions(p.schedule?.conditions || '')
    setSchedEnabled(p.schedule?.enabled || false)
    setMemory(p.memory || '')
  }
  function saveInstructions() {
    save(projects().map(p => p.id === openId() ? {
      ...p,
      instructions: instructions(),
      schedule: { enabled: schedEnabled(), date: schedDate(), time: schedTime(), conditions: schedConditions() },
      memory: memory(),
    } : p))
  }

  const current = () => projects().find(p => p.id === openId())

  // ── Vista: dentro de un proyecto ──────────────────────────────────────────
  return (
    <Show when={!openId()} fallback={
      <div class="panel-page" style="max-width:800px">
        <button class="btn btn-ghost" onClick={() => setOpenId(null)} style="margin-bottom:18px">← Proyectos</button>
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px">
          <div class="app-icon" style="width:48px;height:48px"><IconFolder /></div>
          <div style="font-size:24px;font-weight:700">{current()?.name}</div>
        </div>

        <div class="card" style="margin-top:20px">
          <div class="card-title">{t('ui2.proj_instructions')}</div>
          <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">
            Contexto que se añadirá a todas las conversaciones de este proyecto (como los Projects de Claude).
          </div>
          <textarea
            value={instructions()}
            onInput={e => setInstructions(e.target.value)}
            onBlur={saveInstructions}
            placeholder={t('proj.ph_identity')}
            class="g-input"
            style="width:100%;min-height:120px;resize:vertical;font-family:var(--font);line-height:1.6"
          />
          <button class="btn btn-primary" onClick={saveInstructions} style="margin-top:12px">{t('ui2.save_instructions')}</button>
        </div>

        {/* Programación: fecha, hora, condiciones */}
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div class="card-title" style="margin:0"><IconClock />{t('proj.schedule')}</div>
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text-3);cursor:pointer">
              <input type="checkbox" checked={schedEnabled()} onChange={e => { setSchedEnabled(e.target.checked); saveInstructions() }} />
              Activar ejecución programada
            </label>
          </div>
          <div style="font-size:12px;color:var(--text-3);margin-bottom:14px">
            Ejecuta el proyecto automáticamente en una fecha/hora o cuando se cumplan condiciones.
          </div>
          <Show when={schedEnabled()}>
            <div class="anim-slide" style="display:flex;flex-direction:column;gap:12px">
              <div style="display:flex;gap:12px;flex-wrap:wrap">
                <div style="flex:1;min-width:140px">
                  <label style="font-size:11px;color:var(--text-3);display:block;margin-bottom:4px">Fecha</label>
                  <input type="date" value={schedDate()} onInput={e => setSchedDate(e.target.value)} onBlur={saveInstructions}
                    class="g-input" style="width:100%" />
                </div>
                <div style="flex:1;min-width:140px">
                  <label style="font-size:11px;color:var(--text-3);display:block;margin-bottom:4px">Hora</label>
                  <input type="time" value={schedTime()} onInput={e => setSchedTime(e.target.value)} onBlur={saveInstructions}
                    class="g-input" style="width:100%" />
                </div>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-3);display:block;margin-bottom:4px">{t('proj.exec_cond')}</label>
                <textarea value={schedConditions()} onInput={e => setSchedConditions(e.target.value)} onBlur={saveInstructions}
                  placeholder={t('proj.ph_schedule')}
                  class="g-input" style="width:100%;min-height:70px;resize:vertical;font-family:var(--font);line-height:1.5" />
              </div>
            </div>
          </Show>
        </div>

        {/* Memoria exclusiva del proyecto */}
        <div class="card">
          <div class="card-title"><IconMemory />{t('ui2.proj_memory')}</div>
          <div style="font-size:12px;color:var(--text-3);margin-bottom:12px">
            Información que solo este proyecto recordará. Separada de la memoria global y de otros proyectos.
          </div>
          <textarea
            value={memory()}
            onInput={e => setMemory(e.target.value)}
            onBlur={saveInstructions}
            placeholder={t('proj.ph_context')}
            class="g-input"
            style="width:100%;min-height:100px;resize:vertical;font-family:var(--font);line-height:1.6"
          />
          <button class="btn btn-primary" onClick={saveInstructions} style="margin-top:12px">{t('ui2.save_memory')}</button>
        </div>

        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
            <div class="card-title" style="margin:0">{t('ui2.proj_convs')}</div>
            <button class="btn btn-primary" onClick={() => { props.onNewChat?.(openId()); }}>{t('proj.new_conv')}</button>
          </div>
          <Show when={(current()?.conversationIds || []).length > 0} fallback={
            <div style="text-align:center;padding:32px;color:var(--text-3);font-size:13px">
              Sin conversaciones todavía. Crea una con el botón de arriba.
            </div>
          }>
            <For each={current()?.conversationIds || []}>
              {(cid) => {
                const conv = conversations().find(c => c.id === cid)
                return (
                  <div onClick={() => { loadConversation(cid); props.onOpenChat?.() }}
                    style="padding:12px 14px;border-radius:12px;cursor:pointer;transition:all 0.15s;font-size:14px;color:var(--text-2)"
                    onMouseEnter={e => e.currentTarget.style.background='var(--hover-surface)'}
                    onMouseLeave={e => e.currentTarget.style.background='transparent'}>
                    {conv?.title || 'Conversación'}
                  </div>
                )
              }}
            </For>
          </Show>
        </div>
      </div>
    }>
      <div class="panel-page" style="max-width:900px">
        <div class="panel-page-header">
          <div>
            <div class="panel-page-title">Proyectos</div>
            <div class="panel-page-sub">{t('ui2.proj_group')}</div>
          </div>
          <button class="btn btn-primary" onClick={() => setCreating(true)}>{t('prj.new')}</button>
        </div>

        <Show when={creating()}>
          <div class="card">
            <div class="card-title">{t('ui2.create_project')}</div>
            <input class="g-input" placeholder={t('proj.ph_name')} value={name()}
              onInput={e => setName(e.target.value)} onKeyDown={e => e.key==='Enter' && create()}
              style="margin-bottom:12px" autofocus />
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary" onClick={create}>{t('ui2.create_enter')}</button>
              <button class="btn btn-ghost" onClick={() => { setCreating(false); setName('') }}>{t('btn.cancel')}</button>
            </div>
          </div>
        </Show>

        <Show when={projects().length > 0} fallback={
          <Show when={!creating()}>
            <div class="card" style="text-align:center;padding:48px">
              <div style="opacity:0.25;margin-bottom:16px;display:flex;justify-content:center"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></div>
              <div style="font-size:16px;font-weight:600;margin-bottom:8px">{t('proj.no_projects')}</div>
              <div style="font-size:13px;color:var(--text-3);max-width:380px;margin:0 auto;line-height:1.6">
                Los proyectos agrupan conversaciones relacionadas y comparten contexto e instrucciones.
              </div>
            </div>
          </Show>
        }>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
            <For each={projects()}>
              {(p) => (
                <div class="card" onClick={() => openProject(p)}
                  style="margin-bottom:0;cursor:pointer;position:relative;transition:all 0.18s"
                  onMouseEnter={e => e.currentTarget.style.transform='translateY(-2px)'}
                  onMouseLeave={e => e.currentTarget.style.transform='translateY(0)'}>
                  <div class="app-icon" style="width:42px;height:42px;margin-bottom:12px"><IconFolder /></div>
                  <div style="font-size:15px;font-weight:600;margin-bottom:4px">{p.name}</div>
                  <div style="font-size:12px;color:var(--text-3)">{(p.conversationIds||[]).length} conversaciones</div>
                  <button onClick={(e) => { e.stopPropagation(); remove(p.id) }}
                    style="position:absolute;top:14px;right:14px;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:15px">×</button>
                </div>
              )}
            </For>
          </div>
        </Show>
      </div>
    </Show>
  )
}
