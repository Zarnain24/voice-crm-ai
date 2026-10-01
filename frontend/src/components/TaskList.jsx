import { formatDue } from '../format'

export function TaskList({ tasks, onComplete, onOpenContact }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Open tasks</h2>
        <span className="count">{tasks.length}</span>
      </div>
      {tasks.length === 0 && <p className="empty">You're all caught up.</p>}
      <ul className="task-list">
        {tasks.map((task) => {
          const due = formatDue(task.due_date)
          return (
            <li key={task.id} className="task">
              <button className="check" title="Mark done" aria-label="Mark done" onClick={() => onComplete(task.id)} />
              <div className="task-body">
                <p>{task.title}</p>
                <span className="task-meta">
                  <button className="link" onClick={() => onOpenContact(task.contact_id)}>
                    {task.contact_name}
                  </button>
                  {task.source !== 'ui' && <span className={`badge src-${task.source}`}>{task.source}</span>}
                </span>
              </div>
              <span className={`due due-${due.tone}`}>{due.label}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
