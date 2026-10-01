import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

/**
 * Loads CRM data and keeps it live: the backend pushes every change over Server-Sent
 * Events, and we refetch (debounced) so voice-agent actions appear instantly.
 */
export function useCrm({ onEvent } = {}) {
  const [data, setData] = useState({ pipeline: [], tasks: [], activities: [], contacts: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [live, setLive] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const refresh = useCallback(async () => {
    try {
      const [pipeline, tasks, activities, contacts] = await Promise.all([
        api.pipeline(),
        api.openTasks(),
        api.activities(),
        api.contacts(),
      ])
      setData({ pipeline, tasks, activities, contacts })
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    let timer
    const source = new EventSource('/api/events')
    source.onopen = () => setLive(true)
    source.onerror = () => setLive(false)
    source.onmessage = (message) => {
      onEventRef.current?.(JSON.parse(message.data))
      clearTimeout(timer)
      timer = setTimeout(refresh, 120) // one refetch for a burst of related events
    }
    return () => {
      clearTimeout(timer)
      source.close()
    }
  }, [refresh])

  return { ...data, loading, error, live, refresh }
}
