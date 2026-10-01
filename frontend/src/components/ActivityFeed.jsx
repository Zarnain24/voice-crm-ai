import { timeAgo } from '../format'

const ICONS = {
  stage_changed: '→',
  task_created: '＋',
  task_rescheduled: '↻',
  task_completed: '✓',
  tasks_closed: '✓',
  note: '✎',
  lead_created: '★',
  opportunity_created: '$',
  opportunity_updated: '$',
}

export function ActivityFeed({ activities }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Activity</h2>
      </div>
      <ul className="feed">
        {activities.map((a) => (
          <li key={a.id}>
            <span className={`feed-icon src-${a.source}`}>{ICONS[a.kind] ?? '•'}</span>
            <div>
              <p>{a.message}</p>
              <span className="feed-meta">
                {a.source} · {timeAgo(a.created_at)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
