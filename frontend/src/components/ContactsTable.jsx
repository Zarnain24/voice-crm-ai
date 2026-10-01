import { useMemo, useState } from 'react'
import { initials } from '../format'

export function ContactsTable({ contacts, pipeline, onOpenContact }) {
  const [query, setQuery] = useState('')

  const stageByContact = useMemo(() => {
    const map = {}
    for (const col of pipeline) for (const opp of col.opportunities) (map[opp.contact_id] ??= []).push(opp.stage)
    return map
  }, [pipeline])

  const q = query.trim().toLowerCase()
  const rows = q
    ? contacts.filter((c) => [c.name, c.title, c.company, c.email].some((v) => v?.toLowerCase().includes(q)))
    : contacts

  return (
    <div className="panel contacts">
      <div className="panel-head">
        <h2>Contacts</h2>
        <input className="search" placeholder="Search name, title, utility, email…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Utility</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Deals</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} onClick={() => onOpenContact(c.id)}>
              <td>
                <span className="avatar">{initials(c.name)}</span>
                {c.name}
              </td>
              <td>{c.title ?? '—'}</td>
              <td>{c.company ?? '—'}</td>
              <td>{c.email ?? '—'}</td>
              <td>{c.phone ?? '—'}</td>
              <td>
                {(stageByContact[c.id] ?? []).map((stage, i) => (
                  <span key={i} className={`pill stage-${stage.toLowerCase()}`}>
                    {stage}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="empty">No contacts match "{query}".</p>}
    </div>
  )
}
