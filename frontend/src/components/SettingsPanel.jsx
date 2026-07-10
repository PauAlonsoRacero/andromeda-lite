/**
 * SettingsPanel.jsx — Configuración estilo ajustes de Claude.
 * Secciones a la izquierda, contenido a la derecha con toggles.
 * Incluye: General, MCP Tools, Memoria, Contexto, Alertas, Visuales, Código.
 */
import { createSignal, Show, For, onMount } from 'solid-js'
import * as S from '../stores/settings'
import { session, authRequired, logout } from '../stores/auth'
import { editionLabel, isPro, editionHolder } from '../stores/edition'
import { t, lang, setLang, LANGS } from '../stores/i18n.js'
import { exportConversations, importConversations } from '../stores/chat'
import axios from 'axios'
import ContextPanel from './ContextPanel.jsx'
import MemoryPanel  from './MemoryPanel.jsx'
import ABPanel      from './ABPanel.jsx'
import InfoButton from './InfoButton.jsx'
import RegistryPanel from './RegistryPanel.jsx'
import ProfilePanel from './ProfilePanel.jsx'
import AlertsWidget from './AlertsWidget.jsx'
import MCPPanel     from './MCPPanel.jsx'
import ModelsPanel  from './ModelsPanel.jsx'

const SIcon = (props) => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{props.children}</svg>
)
const SECTIONS = [
  { id: 'general',    label: 'General',      icon: () => <SIcon><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></SIcon> },
  { id: 'appearance', label: 'Apariencia',   icon: () => <SIcon><circle cx="13.5" cy="6.5" r="2.5"/><circle cx="6.5" cy="12" r="2.5"/><circle cx="15" cy="16" r="2.5"/><path d="M12 2a10 10 0 1 0 0 20"/></SIcon> },
  { id: 'models',     label: 'Modelos de IA', icon: () => <SIcon><path d="M12 2 L2 7l10 5 10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></SIcon> },
  { id: 'mcp',        label: 'MCP Tools',    icon: () => <SIcon><path d="M14 6l-4.22 5.63 1.25 1.67L8 16H4l4-5.34L6.75 9 11 3.34 14 6z"/><path d="M20 12l-3 4h-4l3-4z"/></SIcon> },
  { id: 'memory',     label: 'Memoria',      icon: () => <SIcon><path d="M9 3a3 3 0 0 0-3 3v0a3 3 0 0 0-3 3 3 3 0 0 0 1 5.83V18a3 3 0 0 0 5 2 3 3 0 0 0 5-2v-3.17A3 3 0 0 0 18 9a3 3 0 0 0-3-3 3 3 0 0 0-6 0z"/></SIcon> },
  { id: 'capabilities', label: 'Capacidades', icon: () => <SIcon><path d="M13 2L3 14h7l-1 8 10-12h-7z"/></SIcon> },
  { id: 'abtesting', label: 'A/B Testing', icon: () => <SIcon><path d="M3 3v18h18"/><path d="M7 14l3-3 3 2 5-6"/></SIcon> },
  { id: 'registry',  label: 'Model Registry', icon: () => <SIcon><path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/></SIcon> },
  { id: 'alerts',     label: 'Alertas',      icon: () => <SIcon><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></SIcon> },
  { id: 'plan',       label: 'Plan',         icon: () => <SIcon><path d="M12 2l2.4 7.4H22l-6 4.5 2.3 7.1-6.3-4.6L5.7 21 8 14 2 9.4h7.6z"/></SIcon> },
]

// ── Capacidades (toggles funcionales que gatean comportamiento del backend) ──
function CapabilitiesSettings() {
  return (
    <div class="panel-page" style="max-width:760px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px"><div style="font-size:22px;font-weight:700">{t('cap.title')}</div><InfoButton title={t('cap.title')} intro={t('info.cap.intro')} tip={t('info.cap.tip')} items={[
        { h: t('info.cap.1h'), d: t('info.cap.1d') },
        { h: t('info.cap.2h'), d: t('info.cap.2d') },
        { h: t('info.cap.3h'), d: t('info.cap.3d') },
        { h: t('info.cap.4h'), d: t('info.cap.4d') },
      ]} /></div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:18px">{t('cap.sub')}</div>

      {/* Memoria */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:18px 0 4px">{t('cap.memory')}</div>
      <SettingRow title={t('cap.mem_autogen')} desc={t('cap.mem_autogen_d')}>
        <Toggle checked={S.memAutogenerate()} onChange={S.setMemAutogenerate} />
      </SettingRow>
      <SettingRow title={t('cap.mem_search')} desc={t('cap.mem_search_d')}>
        <Toggle checked={S.memConversationSearch()} onChange={S.setMemConversationSearch} />
      </SettingRow>

      {/* Visuales */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('cap.visuals')}</div>
      <SettingRow title={t('cap.artifacts')} desc={t('cap.artifacts_d')}>
        <Toggle checked={S.artifactsEnabled()} onChange={S.setArtifactsEnabled} />
      </SettingRow>
      <SettingRow title={t('cap.inline_viz')} desc={t('cap.inline_viz_d')}>
        <Toggle checked={S.inlineViz()} onChange={S.setInlineViz} />
      </SettingRow>

      {/* Ejecución de archivos y red */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('cap.exec')}</div>
      <SettingRow title={t('cap.file_creation')} desc={t('cap.file_creation_d')}>
        <Toggle checked={S.fileCreation()} onChange={S.setFileCreation} />
      </SettingRow>
      <SettingRow title={t('cap.network')} desc={t('cap.network_d')}>
        <Toggle checked={S.networkEgress()} onChange={S.setNetworkEgress} />
      </SettingRow>

      {/* General */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('cap.general')}</div>
      <SettingRow title={t('cap.model_fallback')} desc={t('cap.model_fallback_d')}>
        <Toggle checked={S.modelFallback()} onChange={S.setModelFallback} />
      </SettingRow>

      <div style="margin-top:20px;padding:12px 14px;border-radius:10px;background:var(--surface-1);border:1px solid var(--hairline);font-size:12px;color:var(--text-3);line-height:1.6">
        {t('cap.note')}
      </div>
    </div>
  )
}

export default function SettingsPanel(props) {
  const [section, setSection] = createSignal(props?.initialSection || 'general')

  return (
    <div style="height:100%;display:flex;overflow:hidden">
      {/* Sub-navegación izquierda */}
      <div style="width:220px;flex-shrink:0;padding:24px 12px;border-right:1px solid var(--glass-border);overflow-y:auto">
        <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;padding:0 12px 12px">{t("settings.title")}</div>
        <For each={SECTIONS}>
          {(s) => (
            <button
              onClick={() => setSection(s.id)}
              style={{
                display: 'flex', 'align-items': 'center', gap: '11px',
                padding: '9px 12px', 'border-radius': '11px', width: '100%',
                border: 'none', 'text-align': 'left', cursor: 'pointer',
                transition: 'all 0.15s', 'margin-bottom': '2px',
                background: section() === s.id ? 'var(--hover-surface)' : 'transparent',
                color: section() === s.id ? 'var(--text-1)' : 'var(--text-2)',
              }}
              onMouseEnter={e => { if(section()!==s.id) e.currentTarget.style.background='var(--hover-surface)' }}
              onMouseLeave={e => { if(section()!==s.id) e.currentTarget.style.background='transparent' }}
            >
              <span style="display:flex;width:18px;justify-content:center">{s.icon()}</span>
              <span style="font-size:14px;font-weight:500">{t('settings.' + (s.id === 'mcp' ? 'mcp' : s.id)) || s.label}</span>
            </button>
          )}
        </For>
      </div>

      {/* Contenido derecha */}
      <div class="cfg-content" style="flex:1;overflow-y:auto">
        <Show when={section()==='general'}><GeneralSettings onOpenProfile={() => setSection('profile')} onOpenAppearance={() => setSection('appearance')} /></Show>
        <Show when={section()==='profile'}><ProfilePanel /></Show>
        <Show when={section()==='appearance'}><AppearanceSettings /></Show>
        <Show when={section()==='models'}><ModelsPanel /></Show>
        <Show when={section()==='mcp'}><MCPPanel /></Show>
        <Show when={section()==='memory'}><div><MemoryPanel /><div style="height:8px" /><ContextPanel /></div></Show>
        <Show when={section()==='capabilities'}><CapabilitiesSettings /></Show>
        <Show when={section()==='abtesting'}><ABPanel /></Show>
        <Show when={section()==='registry'}><RegistryPanel /></Show>
        <Show when={section()==='alerts'}><AlertsWidget /></Show>
        <Show when={section()==='plan'}><PlanSettings /></Show>
      </div>
    </div>
  )
}

// ── Toggle estilo iOS ──────────────────────────────────────────────────────
function Toggle(props) {
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

function SettingRow(props) {
  return (
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:16px 0;border-bottom:1px solid var(--glass-border)">
      <div style="flex:1">
        <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:3px">{props.title}</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.5">{props.desc}</div>
      </div>
      <div style="flex-shrink:0;padding-top:2px">{props.children}</div>
    </div>
  )
}

// ── General ────────────────────────────────────────────────────────────────
function GeneralSettings(props) {
  // Todos los ajustes viven en el store compartido (stores/settings.js)
  const [userMenu, setUserMenu] = createSignal(false)
  const [acctMsg, setAcctMsg] = createSignal(false)

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="font-size:22px;font-weight:700;margin-bottom:6px">{t('settings.general')}</div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:24px">{t('set.general_title')}</div>

      <Show when={session()}>
        <div class="card" style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:20px;position:relative">
          <button onClick={() => setUserMenu(v => !v)}
            style="display:flex;align-items:center;gap:14px;min-width:0;background:none;border:none;cursor:pointer;text-align:left;flex:1;padding:0;font-family:var(--font)"
            title={t('set.account_opts')}>
            <div style="width:42px;height:42px;border-radius:50%;background:var(--grad-primary);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:17px;color:#fff;flex-shrink:0">
              {(session()?.username || '?')[0].toUpperCase()}
            </div>
            <div style="min-width:0">
              <div style="font-size:14px;font-weight:600;color:var(--text-1);overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px">
                {session()?.username}
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style={`transition:transform .2s;transform:rotate(${userMenu() ? 180 : 0}deg)`}><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div style="font-size:11px;color:var(--text-3)">
                Plan <span style={`font-weight:700;${session()?.plan === 'pro' ? 'color:var(--purple)' : 'color:var(--text-2)'}`}>{(session()?.plan || 'free').toUpperCase()}</span>
              </div>
            </div>
          </button>

          {/* Menú desplegable */}
          <Show when={userMenu()}>
            <div style="position:absolute;top:100%;left:14px;margin-top:8px;min-width:240px;background:var(--bg-2);border:1px solid var(--glass-border);border-radius:14px;box-shadow:var(--shadow-lg);padding:6px;z-index:50;animation:fadeUp .18s ease">
              <button onClick={() => { setUserMenu(false); props.onOpenProfile?.() }}
                style="display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border-radius:10px;background:none;border:none;cursor:pointer;color:var(--text-1);font-size:13px;font-family:var(--font);text-align:left"
                onMouseEnter={e => e.currentTarget.style.background='var(--hover-surface)'}
                onMouseLeave={e => e.currentTarget.style.background='none'}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                Ver y editar perfil
              </button>
              <button onClick={() => { setUserMenu(false); props.onOpenAppearance?.() }}
                style="display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border-radius:10px;background:none;border:none;cursor:pointer;color:var(--text-1);font-size:13px;font-family:var(--font);text-align:left"
                onMouseEnter={e => e.currentTarget.style.background='var(--hover-surface)'}
                onMouseLeave={e => e.currentTarget.style.background='none'}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                Apariencia
              </button>
              <div style="height:1px;background:var(--hairline);margin:4px 8px" />
              <button onClick={() => { setUserMenu(false); logout() }}
                style="display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border-radius:10px;background:none;border:none;cursor:pointer;color:var(--red);font-size:13px;font-family:var(--font);text-align:left"
                onMouseEnter={e => e.currentTarget.style.background='var(--hover-surface)'}
                onMouseLeave={e => e.currentTarget.style.background='none'}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                Cerrar sesión
              </button>
            </div>
          </Show>
        </div>
      </Show>

      {/* Sin sesión: cuentas todavía no disponibles en Lite (llegan con Pro) */}
      <Show when={!session()}>
        <div class="card" style="margin-bottom:20px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap">
            <div style="display:flex;align-items:center;gap:14px;min-width:0">
              <div style="width:42px;height:42px;border-radius:50%;background:var(--hover-surface);display:flex;align-items:center;justify-content:center;flex-shrink:0">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </div>
              <div style="min-width:0">
                <div style="font-size:14px;font-weight:600;color:var(--text-1)">{t('gen.account')}</div>
                <div style="font-size:11.5px;color:var(--text-3)">{t('set.local_hint')}</div>
              </div>
            </div>
            <button class="btn btn-glass" style="font-size:13px" onClick={() => setAcctMsg(v => !v)}>{t('ui2.create_account')}</button>
          </div>
          <Show when={acctMsg()}>
            <div class="ios-note" style="margin-top:12px;font-size:12px;display:flex;align-items:flex-start;gap:8px">
              <span style="flex-shrink:0">🚧</span>
              <span>{t('ui2.cloud_soon')}<b>Andromeda Pro</b>{t('set.sync_note')}</span>
            </div>
          </Show>
        </div>
      </Show>

      <Show when={isPro()}>
        <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:8px 0 4px">{t('set.advanced')}</div>
        <SettingRow title={t('set.advanced_mode')} desc={t('gen.advanced_desc')}>
          <Toggle checked={S.advancedMode()} onChange={S.setAdvancedMode} />
        </SettingRow>
        <Show when={S.advancedMode()}>
          <div class="ios-note ios-note-ok" style="margin-bottom:20px;font-size:12px">
            Laboratorio de IA, Estadísticas y MLOps activados. Aparecerán en la barra lateral.
          </div>
        </Show>
      </Show>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('ui2.chat_behavior')}</div>
      <SettingRow title={t('set.streaming_tok')} desc={t('gen.stream_desc')}>
        <Toggle checked={S.streamTokens()} onChange={S.setStreamTokens} />
      </SettingRow>
      <SettingRow title={t('set.auto_title')} desc={t('gen.autotitle_desc')}>
        <Toggle checked={S.autoTitle()} onChange={S.setAutoTitle} />
      </SettingRow>
      <SettingRow title={t('set.save_history')} desc={t('gen.persist_desc')}>
        <Toggle checked={S.saveHistory()} onChange={S.setSaveHistory} />
      </SettingRow>
      <SettingRow title={t('set.backup_migrate')} desc={t('gen.backup_desc')}>
        <div style="display:flex;gap:8px">
          <button class="btn btn-glass" style="font-size:12px" onClick={async () => {
            try {
              const r = await exportConversations()
              if (r?.method === 'file') {
                alert(`Backup guardado en:\n${r.path}\n\n(${r.conversations} conversaciones, ${r.memories} memorias)`)
              }
            } catch (e) { alert('No se pudo exportar: ' + (e?.message || 'error')) }
          }}>{t('set.export')}</button>
          <button class="btn btn-glass" style="font-size:12px" onClick={() => document.getElementById('conv-import').click()}>{t('set.restore')}</button>
          <input id="conv-import" type="file" accept="application/json" style="display:none"
            onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return
              try {
                const r = await importConversations(await f.text())
                const parts = []
                if (r.conversations > 0) parts.push(`${r.conversations} conversaciones`)
                if (r.memories > 0) parts.push(`${r.memories} memorias`)
                alert(parts.length ? `Se restauraron ${parts.join(' y ')}.` : 'No había nada nuevo que restaurar.')
              } catch (err) { alert('No se pudo restaurar: ' + err.message) }
              e.target.value = ''
            }} />
        </div>
      </SettingRow>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('set.chat_view')}</div>
      <SettingRow title={t('set.show_latency')} desc={t('gen.show_latency_desc')}>
        <Toggle checked={S.showLatency()} onChange={S.setShowLatency} />
      </SettingRow>
      <Show when={isPro()}>
        <SettingRow title={t('set.spec_badges')} desc={t('gen.showais_desc')}>
          <Toggle checked={S.showBadges()} onChange={S.setShowBadges} />
        </SettingRow>
      </Show>
      <SettingRow title={t('set.compact_mode')} desc={t('gen.compact_desc')}>
        <Toggle checked={S.compactMode()} onChange={S.setCompactMode} />
      </SettingRow>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{isPro() ? t('gen.orchestration') : t('gen.responses')}</div>
      <Show when={isPro()}>
        <SettingRow title={t('set.parallel_default')} desc={t('gen.parallel_desc')}>
          <Selector value={S.defaultParallel()} onChange={S.setDefaultParallel} options={[['auto','Auto'],['1','1'],['2','2'],['3','3'],['4','4']]} />
        </SettingRow>
      </Show>
      <SettingRow title={`${t('gen.temperature')}: ${S.temperature().toFixed(1)}`} desc={t('gen.temp_desc')}>
        <input type="range" min="0" max="1.5" step="0.1" value={S.temperature()}
          onInput={e => S.setTemperature(parseFloat(e.target.value))}
          style="width:120px;accent-color:var(--blue)" />
      </SettingRow>

    </div>
  )
}

function Selector(props) {
  return (
    <select value={props.value} onChange={e => props.onChange(e.target.value)}
      class="g-input" style="width:auto;min-width:120px;font-size:13px;padding:6px 10px">
      <For each={props.options}>{(o) => <option value={o[0]}>{o[1]}</option>}</For>
    </select>
  )
}

// ── Apariencia (tema, orbes, código) ────────────────────────────────────────
const ORB_PRESETS = [
  { id: 'aurora', label: t('orb.aurora'), colors: ['#f0795f','#5b78f5','#c87bd8'] },
  { id: 'ocean',  label: t('orb.ocean'), colors: ['#38bdf8','#2d6cdf','#22d3aa'] },
  { id: 'sunset', label: t('orb.sunset'), colors: ['#f87159','#ec4899','#fb923c'] },
  { id: 'forest', label: t('orb.forest'), colors: ['#34d399','#84cc16','#10b981'] },
  { id: 'galaxy', label: t('orb.galaxy'), colors: ['#a855f7','#6366f1','#d946ef'] },
  { id: 'mono',   label: t('orb.mono'), colors: ['#94a3b8','#64748b','#cbd5e1'] },
]

function AppearanceSettings() {
  return (
    <div class="panel-page" style="max-width:760px">
      <div style="font-size:22px;font-weight:700;margin-bottom:6px">{t('settings.appearance')}</div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:24px">{t('set.general_sub')}</div>

      {/* Idioma */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:8px 0 10px">{t('settings.language')}</div>
      <div style="font-size:12.5px;color:var(--text-3);margin-bottom:12px">{t('settings.language_desc')}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:26px">
        <For each={LANGS}>
          {(l) => (
            <button onClick={() => setLang(l.id)}
              style={`display:flex;align-items:center;gap:8px;padding:9px 14px;border-radius:12px;cursor:pointer;font-family:var(--font);font-size:13px;font-weight:600;transition:all .15s;
                border:1.5px solid ${lang()===l.id ? 'var(--blue)' : 'var(--glass-border)'};
                background:${lang()===l.id ? 'var(--hover-surface)' : 'transparent'};
                color:${lang()===l.id ? 'var(--text-1)' : 'var(--text-2)'}`}>
              <span style="font-size:10px;font-weight:800;letter-spacing:0.04em;opacity:0.7">{l.flag}</span>
              {l.label}
            </button>
          )}
        </For>
      </div>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:8px 0 10px">{t('settings.appearance')}</div>
      <div style="display:flex;gap:12px;margin-bottom:24px">
        <ThemeCard active={S.theme()==='dark'}  onClick={() => S.setTheme('dark')}  name={t("ui2.theme_dark")} bg="#13141f" fg="#f5f5f7" />
        <ThemeCard active={S.theme()==='light'} onClick={() => S.setTheme('light')} name={t("ui2.theme_light")}  bg="#f4f6fb" fg="#14151f" />
      </div>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:8px 0 4px">{t('ui2.animated_bg')}</div>
      <SettingRow title={t('set.bg_color')} desc={t('set.bg_desc')}>
        <Toggle checked={S.orbsOn()} onChange={S.setOrbsOn} />
      </SettingRow>

      <Show when={S.orbsOn()}>
        <div style="padding:16px 0;border-bottom:1px solid var(--hairline)">
          <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:12px">{t('ui2.bg_style')}</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
            <button onClick={() => S.setBgStyle('bands')}
              style={{
                display:'flex','flex-direction':'column','align-items':'center',gap:'8px',
                padding:'14px','border-radius':'14px',cursor:'pointer',transition:'all .18s',
                border: S.bgStyle()==='bands' ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
                background: S.bgStyle()==='bands' ? 'var(--hover-surface)' : 'transparent',
              }}>
              <div style="position:relative;height:32px;width:56px;overflow:hidden;border-radius:8px">
                <div style="position:absolute;inset:-40%;transform:rotate(40deg)">
                  <div style="position:absolute;top:4%;left:-20%;width:140%;height:26%;background:linear-gradient(90deg,transparent,#f0795f,transparent);filter:blur(3px)" />
                  <div style="position:absolute;top:38%;left:-20%;width:140%;height:26%;background:linear-gradient(90deg,transparent,#c87bd8,transparent);filter:blur(3px)" />
                  <div style="position:absolute;top:72%;left:-20%;width:140%;height:26%;background:linear-gradient(90deg,transparent,#5b78f5,transparent);filter:blur(3px)" />
                </div>
              </div>
              <span style="font-size:12px;font-weight:600;color:var(--text-1)">{t("ui2.bg_bands")}</span>
            </button>
            <button onClick={() => S.setBgStyle('orbs')}
              style={{
                display:'flex','flex-direction':'column','align-items':'center',gap:'8px',
                padding:'14px','border-radius':'14px',cursor:'pointer',transition:'all .18s',
                border: S.bgStyle()==='orbs' ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
                background: S.bgStyle()==='orbs' ? 'var(--hover-surface)' : 'transparent',
              }}>
              <div style="position:relative;height:32px;width:56px;overflow:hidden;border-radius:8px">
                <span style="position:absolute;width:24px;height:24px;border-radius:50%;background:#f0795f;filter:blur(4px);top:-2px;left:2px" />
                <span style="position:absolute;width:22px;height:22px;border-radius:50%;background:#c87bd8;filter:blur(4px);bottom:-2px;left:16px" />
                <span style="position:absolute;width:20px;height:20px;border-radius:50%;background:#5b78f5;filter:blur(4px);top:4px;right:2px" />
              </div>
              <span style="font-size:12px;font-weight:600;color:var(--text-1)">{t("ui2.bg_orbs")}</span>
            </button>
            <button onClick={() => S.setBgStyle('waves')}
              style={{
                display:'flex','flex-direction':'column','align-items':'center',gap:'8px',
                padding:'14px','border-radius':'14px',cursor:'pointer',transition:'all .18s',
                border: S.bgStyle()==='waves' ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
                background: S.bgStyle()==='waves' ? 'var(--hover-surface)' : 'transparent',
              }}>
              <div style="position:relative;height:32px;width:56px;overflow:hidden;border-radius:8px">
                <div style="position:absolute;bottom:-30%;left:-10%;width:120%;height:60%;background:radial-gradient(ellipse 60% 100% at 50% 100%,#f0795f,transparent 70%);filter:blur(4px)" />
                <div style="position:absolute;bottom:-20%;left:-10%;width:120%;height:55%;background:radial-gradient(ellipse 60% 100% at 50% 100%,#5b78f5,transparent 70%);filter:blur(4px)" />
                <div style="position:absolute;bottom:-10%;left:-10%;width:120%;height:50%;background:radial-gradient(ellipse 60% 100% at 50% 100%,#c87bd8,transparent 70%);filter:blur(4px)" />
              </div>
              <span style="font-size:12px;font-weight:600;color:var(--text-1)">{t("ui2.bg_waves")}</span>
            </button>
          </div>

          {/* Nº de colores cuando el estilo es Olas */}
          <Show when={S.bgStyle()==='waves'}>
            <div style="margin-top:14px">
              <div style="font-size:12px;color:var(--text-3);margin-bottom:8px">{t('ui2.wave_colors')}</div>
              <div style="display:flex;gap:8px">
                <For each={[2,3,4]}>
                  {(n) => (
                    <button onClick={() => S.setWaveCount(n)}
                      style={{
                        flex:'1',padding:'8px','border-radius':'10px',cursor:'pointer',transition:'all .15s',
                        'font-size':'13px','font-weight':'600',
                        border: S.waveCount()===n ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
                        background: S.waveCount()===n ? 'var(--hover-surface)' : 'transparent',
                        color: S.waveCount()===n ? 'var(--text-1)' : 'var(--text-3)',
                      }}>{n} {t('ui2.colors')}</button>
                  )}
                </For>
              </div>
              {/* Altura de las olas */}
              <div style="margin-top:14px">
                <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text-3);margin-bottom:6px">
                  <span>{t('ui2.wave_height')}</span><span>{S.waveHeight()}%</span>
                </div>
                <input type="range" min="30" max="70" step="5" value={S.waveHeight()}
                  onInput={e => S.setWaveHeight(Number(e.currentTarget.value))}
                  style="width:100%;accent-color:var(--blue);cursor:pointer" />
              </div>
            </div>
          </Show>
        </div>
      </Show>

      <Show when={S.orbsOn() && S.bgStyle()==='orbs'}>
        <div style="padding:16px 0;border-bottom:1px solid var(--hairline)" classList={{ 'orb-palette-hidden': S.orbCustom() }}>
          <Show when={!S.orbCustom()}>
          <div style="font-size:14px;font-weight:600;color:var(--text-1);margin-bottom:12px">{t('ui2.orb_palette')}</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
            <For each={ORB_PRESETS}>
              {(p) => (
                <button
                  onClick={() => S.setOrbPalette(p.id)}
                  style={{
                    display:'flex','flex-direction':'column','align-items':'center',gap:'8px',
                    padding:'12px','border-radius':'14px',cursor:'pointer',transition:'all .18s',
                    border: S.orbPalette()===p.id ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
                    background: S.orbPalette()===p.id ? 'var(--hover-surface)' : 'transparent',
                  }}
                >
                  <div style="display:flex;gap:-6px;position:relative;height:28px;width:56px;justify-content:center">
                    <span style={`width:28px;height:28px;border-radius:50%;background:${p.colors[0]};filter:blur(2px);position:absolute;left:0`} />
                    <span style={`width:28px;height:28px;border-radius:50%;background:${p.colors[1]};filter:blur(2px);position:absolute;left:14px`} />
                    <span style={`width:28px;height:28px;border-radius:50%;background:${p.colors[2]};filter:blur(2px);position:absolute;left:28px`} />
                  </div>
                  <span style={`font-size:12px;font-weight:600;color:${S.orbPalette()===p.id?'var(--text-1)':'var(--text-2)'}`}>{p.label}</span>
                </button>
              )}
            </For>
          </div>
          </Show>
        </div>

        <SettingRow title={`Velocidad: ${S.orbSpeed().toFixed(1)}×`} desc={t('set.orbspeed_desc')}>
          <input type="range" min="0.4" max="2" step="0.1" value={S.orbSpeed()}
            onInput={e => S.setOrbSpeed(parseFloat(e.target.value))}
            style="width:140px;accent-color:var(--blue)" />
        </SettingRow>
        <SettingRow title={`Intensidad: ${Math.round(S.orbIntensity()*100)}%`} desc={t('set.orbintensity_desc')}>
          <input type="range" min="0.4" max="1.4" step="0.1" value={S.orbIntensity()}
            onInput={e => S.setOrbIntensity(parseFloat(e.target.value))}
            style="width:140px;accent-color:var(--blue)" />
        </SettingRow>
        <SettingRow title={`Tamaño: ${Math.round(S.orbSize()*100)}%`} desc={t('set.orbsize_desc')}>
          <input type="range" min="0.5" max="1.8" step="0.1" value={S.orbSize()}
            onInput={e => S.setOrbSize(parseFloat(e.target.value))}
            style="width:140px;accent-color:var(--blue)" />
        </SettingRow>
        <SettingRow title={t('set.custom_colors')} desc={t('set.customcolors_desc')}>
          <Toggle checked={S.orbCustom()} onChange={S.setOrbCustom} />
        </SettingRow>
        <Show when={S.orbCustom()}>
          <div style="display:flex;gap:14px;padding:4px 0 16px;align-items:center">
            <For each={[0,1,2]}>
              {(i) => (
                <label style="display:flex;flex-direction:column;align-items:center;gap:6px;font-size:11px;color:var(--text-3);cursor:pointer">
                  Orbe {i+1}
                  <input type="color" value={S.orbColors()[i]}
                    onInput={e => { const c = [...S.orbColors()]; c[i] = e.target.value; S.setOrbColors(c) }}
                    style="width:44px;height:44px;border:none;border-radius:12px;background:none;cursor:pointer;padding:0" />
                </label>
              )}
            </For>
          </div>
        </Show>
      </Show>

      <SettingRow title={t('set.ui_anim')} desc={t('set.animations_desc')}>
        <Toggle checked={S.animationsOn()} onChange={S.setAnimationsOn} />
      </SettingRow>

      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin:24px 0 4px">{t('set.code_blocks')}</div>
      <SettingRow title={t('set.syntax_hl')} desc={t('set.codecolor_desc')}>
        <Toggle checked={S.syntaxHl()} onChange={S.setSyntaxHl} />
      </SettingRow>
      <SettingRow title={t('set.line_numbers')} desc={t('set.linenums_desc')}>
        <Toggle checked={S.lineNumbers()} onChange={S.setLineNumbers} />
      </SettingRow>
    </div>
  )
}

function ThemeCard(props) {
  return (
    <button
      onClick={props.onClick}
      style={{
        flex: 1, padding: '4px', 'border-radius': '16px', cursor: 'pointer',
        transition: 'all .18s', background: 'transparent',
        border: props.active ? '1.5px solid var(--blue)' : '1px solid var(--glass-border)',
      }}
    >
      <div style={{
        height: '76px', 'border-radius': '12px', background: props.bg,
        display: 'flex', 'align-items': 'center', 'justify-content': 'center',
        'box-shadow': 'inset 0 1px 0 rgba(255,255,255,0.1)', 'margin-bottom': '8px',
      }}>
        <span style={{ 'font-family': 'Playfair Display, Georgia, serif', 'font-size': '20px', 'font-weight': 600, color: props.fg }}>Aa</span>
      </div>
      <div style={`font-size:13px;font-weight:600;padding-bottom:6px;color:${props.active?'var(--text-1)':'var(--text-2)'}`}>{props.name}</div>
    </button>
  )
}

// ── Plan (Lite / Pro) ────────────────────────────────────────────────────────
function PlanSettings() {
  const [cat, setCat] = createSignal([])
  onMount(async () => {
    try { const r = await axios.get('/api/edition/catalog'); setCat(r.data.features || []) } catch {}
  })

  const Check = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
  const Dash  = () => <span style="color:var(--text-3);font-size:15px">—</span>

  return (
    <div class="panel-page" style="max-width:760px">
      <div style="font-size:22px;font-weight:700;margin-bottom:6px">{t('settings.plan')}</div>
      <div style="font-size:13px;color:var(--text-3);margin-bottom:20px">{t('set.edition_sub')}</div>

      {/* Edición activa */}
      <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:22px">
        <div style="display:flex;align-items:center;gap:14px">
          <div style="width:44px;height:44px;border-radius:12px;background:var(--grad-primary);display:flex;align-items:center;justify-content:center;flex-shrink:0">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"><path d="M12 2l2.4 7.4H22l-6 4.5 2.3 7.1-6.3-4.6L5.7 21 8 14 2 9.4h7.6z"/></svg>
          </div>
          <div>
            <div style="font-size:16px;font-weight:700;color:var(--text-1)">{editionLabel()}</div>
            <div style="font-size:12px;color:var(--text-3)">
              <Show when={isPro()} fallback={t('plan.lite_tagline')}>
                {editionHolder() ? `Licencia: ${editionHolder()}` : 'Edición comercial activa'}
              </Show>
            </div>
          </div>
        </div>
        <Show when={!isPro()}>
          <a href="https://github.com/" target="_blank" class="btn btn-primary" style="text-decoration:none;background:var(--grad-primary);color:#fff">{t('plan.know_pro')}</a>
        </Show>
      </div>

      {/* Comparativa */}
      <div style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px">{t('plan.comparison')}</div>
      <div class="card" style="padding:0;overflow:hidden">
        <div style="display:grid;grid-template-columns:1fr 80px 80px;gap:0;align-items:center;padding:12px 16px;border-bottom:1px solid var(--hairline);font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:0.04em">
          <span>{t('set.feature')}</span>
          <span style="text-align:center">Lite</span>
          <span style="text-align:center">Pro</span>
        </div>
        <For each={cat()}>
          {(f) => (
            <div style="display:grid;grid-template-columns:1fr 80px 80px;gap:0;align-items:center;padding:13px 16px;border-bottom:1px solid var(--hairline)">
              <div style="min-width:0">
                <div style="font-size:13.5px;font-weight:600;color:var(--text-1)">{(() => { const k=`plan.${f.key}.label`; const v=t(k); return v!==k?v:f.label })()}</div>
                <Show when={f.description}><div style="font-size:11.5px;color:var(--text-3);margin-top:2px">{(() => { const k=`plan.${f.key}.desc`; const v=t(k); return v!==k?v:f.description })()}</div></Show>
              </div>
              <div style="display:flex;justify-content:center"><Show when={f.lite} fallback={<Dash/>}><Check/></Show></div>
              <div style="display:flex;justify-content:center"><Show when={f.pro} fallback={<Dash/>}><Check/></Show></div>
            </div>
          )}
        </For>
      </div>

      <div class="proj-note" style="margin-top:16px">
        Lite es un producto completo para uso individual y 100% local — sin recortes en el motor de
        orquestación. Pro añade la capa de equipo (multiusuario, observabilidad agregada, SSO, auditoría)
        más soporte y consultoría, pensada para empresas que despliegan Andromeda on-premise.
      </div>
    </div>
  )
}
