import { lazy, Suspense, useState } from 'react'
import { api } from '../api'

// LiveKit is the heaviest dependency; load it only once a session starts.
const VoiceSession = lazy(() => import('./VoiceSession'))

const EXAMPLES = [
  'Move John Smith to Qualified and create a follow-up for tomorrow.',
  "What's due today?",
  'Add a note to Zarnain Khalique: wants monthly revenue reports by rate class.',
  'Give me a pipeline summary.',
]

export function VoicePanel({ onError }) {
  const [session, setSession] = useState(null)
  const [starting, setStarting] = useState(false)

  const start = async () => {
    setStarting(true)
    try {
      setSession(await api.voiceToken())
    } catch (e) {
      onError(`Voice unavailable: ${e.message}`)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="panel voice">
      <div className="panel-head">
        <h2>Voice assistant</h2>
        <span className="muted small">LiveKit · Deepgram · Groq</span>
      </div>

      {session ? (
        <Suspense fallback={<p className="empty">Connecting…</p>}>
          <VoiceSession session={session} examples={EXAMPLES} onEnd={() => setSession(null)} onError={onError} />
        </Suspense>
      ) : (
        <>
          <button className="btn primary mic-btn" onClick={start} disabled={starting}>
            <span className="mic-icon" aria-hidden>
              ●
            </span>
            {starting ? 'Starting…' : 'Start voice session'}
          </button>
          <p className="hint">Try saying:</p>
          <ul className="examples">
            {EXAMPLES.map((ex) => (
              <li key={ex}>“{ex}”</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
