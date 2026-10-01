// All calls go through the Vite proxy (/api -> FastAPI), which attaches the API key.

async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const { detail } = await res.json()
      message = typeof detail === 'string' ? detail : detail.map((e) => `${e.loc.at(-1)}: ${e.msg}`).join(', ')
    } catch {
      /* keep status text */
    }
    throw new Error(message)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  pipeline: () => request('/pipeline'),
  openTasks: () => request('/tasks?status=open'),
  activities: (limit = 40) => request(`/activities?limit=${limit}`),
  contacts: () => request('/contacts'),
  contact: (id) => request(`/contacts/${id}`),
  createContact: (data) => request('/contacts', { method: 'POST', body: data }),
  moveStage: (opportunityId, stage) =>
    request(`/opportunities/${opportunityId}/stage`, { method: 'PATCH', body: { stage } }),
  completeTask: (id) => request(`/tasks/${id}/complete`, { method: 'POST' }),
  addNote: (contactId, text) => request(`/contacts/${contactId}/notes`, { method: 'POST', body: { text } }),
  voiceToken: () => request('/voice/token', { method: 'POST' }),
}
