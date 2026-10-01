import { useState } from 'react'
import { formatMoney } from '../format'

/** Kanban board. Cards can be dragged between stages; `highlightId` pulses a card
 *  that was just changed elsewhere (e.g. by the voice agent). */
export function Pipeline({ columns, highlightId, onMove, onOpenContact }) {
  const [dragOver, setDragOver] = useState(null)

  const drop = (event, stage) => {
    event.preventDefault()
    setDragOver(null)
    const { id, from } = JSON.parse(event.dataTransfer.getData('application/json'))
    if (from !== stage) onMove(id, stage)
  }

  return (
    <div className="board">
      {columns.map((col) => (
        <section
          key={col.stage}
          className={`column stage-${col.stage.toLowerCase()} ${dragOver === col.stage ? 'drag-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(col.stage)
          }}
          onDragLeave={() => setDragOver(null)}
          onDrop={(e) => drop(e, col.stage)}
        >
          <header className="column-head">
            <span className="stage-dot" />
            <h3>{col.stage}</h3>
            <span className="count">{col.count}</span>
            <span className="column-total">{formatMoney(col.total_value)}</span>
          </header>

          <div className="cards">
            {col.opportunities.map((opp) => (
              <article
                key={opp.id}
                className={`card ${opp.id === highlightId ? 'pulse' : ''}`}
                draggable
                onDragStart={(e) =>
                  e.dataTransfer.setData('application/json', JSON.stringify({ id: opp.id, from: opp.stage }))
                }
                onClick={() => onOpenContact(opp.contact_id)}
              >
                <p className="card-title">{opp.title}</p>
                <div className="card-meta">
                  <span>{opp.contact_name}</span>
                  <strong>{formatMoney(opp.value)}</strong>
                </div>
              </article>
            ))}
            {col.count === 0 && <p className="empty">Drop deals here</p>}
          </div>
        </section>
      ))}
    </div>
  )
}
