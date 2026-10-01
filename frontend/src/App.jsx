import { useCallback, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { describeEvent, formatMoney } from './format'
import { useCrm } from './useCrm'
import { ActivityFeed } from './components/ActivityFeed'
import { ContactDrawer } from './components/ContactDrawer'
import { ContactsTable } from './components/ContactsTable'
import { NewLeadDialog } from './components/NewLeadDialog'
import { Pipeline } from './components/Pipeline'
import { TaskList } from './components/TaskList'
import { VoicePanel } from './components/VoicePanel'

export default function App() {
  const [tab, setTab] = useState('pipeline')
  const [openContactId, setOpenContactId] = useState(null)
  const [showNewLead, setShowNewLead] = useState(false)
  const [highlightId, setHighlightId] = useState(null)
  const [toasts, setToasts] = useState([])
  const [version, setVersion] = useState(0)
  const highlightTimer = useRef()

  const toast = useCallback((text, tone = 'info') => {
    const id = crypto.randomUUID()
    setToasts((t) => [...t, { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])
  const showError = useCallback((message) => toast(message, 'error'), [toast])

  const handleEvent = useCallback(
    (event) => {
      setVersion((v) => v + 1)
      const oppId = event.data.opportunity_id
      if (oppId) {
        setHighlightId(oppId)
        clearTimeout(highlightTimer.current)
        highlightTimer.current = setTimeout(() => setHighlightId(null), 2500)
      }
      // Surface changes that didn't come from this screen (voice, automation, webhooks).
      const text = describeEvent(event)
      if (text && event.data.source && event.data.source !== 'ui') toast(text, event.data.source)
    },
    [toast],
  )

  const crm = useCrm({ onEvent: handleEvent })

  const stats = useMemo(() => {
    const byStage = Object.fromEntries(crm.pipeline.map((c) => [c.stage, c]))
    const open = ['New', 'Contacted', 'Qualified', 'Proposal'].reduce((sum, s) => sum + (byStage[s]?.total_value ?? 0), 0)
    const today = new Date().toLocaleDateString('en-CA')
    return {
      open,
      won: byStage.Won?.total_value ?? 0,
      due: crm.tasks.filter((t) => t.due_date <= today).length,
    }
  }, [crm.pipeline, crm.tasks])

  const moveStage = async (id, stage) => {
    try {
      await api.moveStage(id, stage)
    } catch (e) {
      showError(e.message)
    }
  }

  const completeTask = async (id) => {
    try {
      await api.completeTask(id)
    } catch (e) {
      showError(e.message)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span> Voice CRM
        </div>
        <nav className="tabs">
          {['pipeline', 'contacts'].map((t) => (
            <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
              {t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
        <div className="stats">
          <Stat label="Open pipeline" value={formatMoney(stats.open)} />
          <Stat label="Won" value={formatMoney(stats.won)} />
          <Stat label="Due / overdue" value={stats.due} />
        </div>
        <span className={`live ${crm.live ? 'on' : ''}`} title="Real-time updates">
          {crm.live ? 'Live' : 'Offline'}
        </span>
        <button className="btn primary" onClick={() => setShowNewLead(true)}>
          + New lead
        </button>
      </header>

      {crm.error && <div className="banner">Can't reach the CRM API: {crm.error}</div>}

      <main className="layout">
        <section className="main">
          {crm.loading ? (
            <p className="empty">Loading…</p>
          ) : tab === 'pipeline' ? (
            <Pipeline columns={crm.pipeline} highlightId={highlightId} onMove={moveStage} onOpenContact={setOpenContactId} />
          ) : (
            <ContactsTable contacts={crm.contacts} pipeline={crm.pipeline} onOpenContact={setOpenContactId} />
          )}
        </section>

        <aside className="sidebar">
          <VoicePanel onError={showError} />
          <TaskList tasks={crm.tasks} onComplete={completeTask} onOpenContact={setOpenContactId} />
          <ActivityFeed activities={crm.activities} />
        </aside>
      </main>

      {openContactId && (
        <ContactDrawer contactId={openContactId} version={version} onClose={() => setOpenContactId(null)} onError={showError} />
      )}
      {showNewLead && <NewLeadDialog onClose={() => setShowNewLead(false)} onError={showError} />}

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            {t.tone === 'voice' && '🎙 '}
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
