import { useEffect, useMemo, useRef, useState } from 'react'
import '@livekit/components-styles'
import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  VoiceAssistantControlBar,
  useRoomContext,
  useTranscriptions,
  useVoiceAssistant,
} from '@livekit/components-react'

const STATE_LABEL = {
  disconnected: 'Disconnected',
  connecting: 'Connecting…',
  initializing: 'Agent joining…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
}

export default function VoiceSession({ session, examples, onEnd, onError }) {
  return (
    <LiveKitRoom
      serverUrl={session.server_url}
      token={session.token}
      connect
      audio
      video={false}
      onDisconnected={onEnd}
      onError={(e) => onError(e.message)}
      className="voice-room"
    >
      <RoomAudioRenderer />
      <StartAudio label="Click to enable audio" className="btn" />
      <Assistant examples={examples} />
    </LiveKitRoom>
  )
}

function Assistant({ examples }) {
  const room = useRoomContext()
  const { state, audioTrack } = useVoiceAssistant()
  const transcriptions = useTranscriptions()
  const [typed, setTyped] = useState([])
  const [text, setText] = useState('')
  const logRef = useRef(null)

  // Merge spoken transcripts (both sides) with commands typed into the chat box.
  const messages = useMemo(() => {
    const spoken = transcriptions.map((t) => ({
      id: t.streamInfo.id,
      at: t.streamInfo.timestamp,
      who: t.participantInfo.identity === room.localParticipant.identity ? 'you' : 'agent',
      text: t.text,
    }))
    return [...spoken, ...typed].filter((m) => m.text.trim()).sort((a, b) => a.at - b.at)
  }, [transcriptions, typed, room])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Typed input goes to the same agent over LiveKit's text channel, handy without a mic.
  const send = async (value) => {
    const message = value.trim()
    if (!message) return
    setText('')
    setTyped((prev) => [...prev, { id: `typed-${Date.now()}`, at: Date.now(), who: 'you', text: message }])
    await room.localParticipant.sendText(message, { topic: 'lk.chat' })
  }

  return (
    <div className="assistant">
      <div className="visualizer">
        <BarVisualizer state={state} barCount={7} track={audioTrack} />
        <span className="agent-state">{STATE_LABEL[state] ?? state}</span>
      </div>

      <div className="transcript" ref={logRef}>
        {messages.length === 0 && <p className="empty">Say something, or type a command below.</p>}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.who}`}>
            {m.text}
          </div>
        ))}
      </div>

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a command…" maxLength={500} />
        <button className="btn" disabled={!text.trim()}>
          Send
        </button>
      </form>

      <div className="quick">
        {examples.slice(0, 2).map((ex) => (
          <button key={ex} className="chip" onClick={() => send(ex)}>
            {ex}
          </button>
        ))}
      </div>

      <VoiceAssistantControlBar controls={{ leave: true, microphone: true }} />
    </div>
  )
}
