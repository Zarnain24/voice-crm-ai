import { useEffect, useState } from 'react'
import { api } from '../api'
import { formatDue, formatMoney, initials, timeAgo } from '../format'

/** Side drawer with a contact's deals, tasks and timeline. Refetches when `version` bumps
 *  (i.e. on any live CRM event) so it stays current while the voice agent works. */
export function ContactDrawer({ contactId, version, onClose, onError }) {
  const [contact, setContact] = useState(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .contact(contactId)
      .then((c) => !cancelled && setContact(c))
      .catch((e) => onError(e.message))
    return () => {
      cancelled = true
    }
  }, [contactId, version, onError])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submitNote = async (e) => {
    e.preventDefault()
    if (!note.trim()) return
    try {
      await api.addNote(contactId, note)
      setNote('')
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Contact details">
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>
        {!contact ? (
          <p className="empty">Loading…</p>
        ) : (
          <>
            <header className="drawer-head">
              <span className="avatar lg">{initials(contact.name)}</span>
              <div>
                <h2>{contact.name}</h2>
                <p className="muted">{[contact.title, contact.company, contact.email, contact.phone].filter(Boolean).join(' · ')}</p>
              </div>
            </header>

            <h4>Deals</h4>
            {contact.opportunities.map((o) => (
              <div key={o.id} className="drawer-row">
                <span>{o.title}</span>
                <span className={`pill stage-${o.stage.toLowerCase()}`}>{o.stage}</span>
                <strong>{formatMoney(o.value)}</strong>
              </div>
            ))}
            {contact.opportunities.length === 0 && <p className="empty">No deals.</p>}

            <h4>Open tasks</h4>
            {contact.open_tasks.map((t) => {
              const due = formatDue(t.due_date)
              return (
                <div key={t.id} className="drawer-row">
                  <span>{t.title}</span>
                  <span className={`due due-${due.tone}`}>{due.label}</span>
                </div>
              )
            })}
            {contact.open_tasks.length === 0 && <p className="empty">No open tasks.</p>}

            <h4>Add note</h4>
            <form className="note-form" onSubmit={submitNote}>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={3} placeholder="Call summary, objections, next steps…" />
              <button className="btn primary" disabled={!note.trim()}>
                Save note
              </button>
            </form>

            <h4>Timeline</h4>
            <ul className="feed compact">
              {contact.recent_activity.map((a) => (
                <li key={a.id}>
                  <span className={`feed-icon src-${a.source}`}>•</span>
                  <div>
                    <p>{a.message}</p>
                    <span className="feed-meta">
                      {a.source} · {timeAgo(a.created_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  )
}
