const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const formatMoney = (value) => money.format(value)

export function formatDue(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number)
  const due = new Date(y, m - 1, d)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((due - today) / 86_400_000)
  if (days < 0) return { label: days === -1 ? 'Yesterday' : `${-days} days overdue`, tone: 'overdue' }
  if (days === 0) return { label: 'Today', tone: 'today' }
  if (days === 1) return { label: 'Tomorrow', tone: 'soon' }
  return { label: due.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }), tone: 'later' }
}

export function timeAgo(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export const initials = (name) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')

/** One-line human description of a CRM event, for toasts. */
export function describeEvent({ type, data }) {
  switch (type) {
    case 'opportunity.stage_changed':
      return `${data.contact_name} moved to ${data.to_stage}`
    case 'task.created':
    case 'task.updated':
      return `Follow-up for ${data.contact_name}: ${formatDue(data.due_date).label}`
    case 'task.completed':
      return `Completed: ${data.title}`
    case 'opportunity.created':
      return `New deal for ${data.contact_name}: ${data.title}`
    case 'opportunity.updated':
      return `${data.contact_name}'s deal updated: ${data.title}, ${formatMoney(data.value)}`
    case 'lead.created':
      return `New lead: ${data.name}`
    case 'note.added':
      return `Note added to ${data.contact_name}`
    default:
      return null
  }
}
