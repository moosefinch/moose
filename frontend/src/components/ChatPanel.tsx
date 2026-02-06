import { useEffect, useRef, useCallback } from 'react'
import { MessageBubble } from './MessageBubble'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ChatInput } from './ChatInput'
import { AvatarPresence } from './AvatarPresence'
import { useTTS } from '../hooks/useTTS'
import type { ChatMessage, CognitiveStatus } from '../types'

interface Props {
  messages: ChatMessage[]
  sending: boolean
  loading: boolean
  activeModel: string
  thinkingElapsed: number
  endRef: React.RefObject<HTMLDivElement | null>
  onSend: (text: string) => void
  onVoiceStart?: () => void
  isRecording?: boolean
  cognitiveStatus?: CognitiveStatus | null
}

/** Only show messages that represent "brain activity" — not conversation content */
function isBrainActivity(m: ChatMessage): boolean {
  if (m.role === 'notification') return true
  if (m.role === 'proactive' || m.proactive_category) return true
  if (m.role === 'assistant' && ((m.tool_calls && m.tool_calls.length > 0) || m.plan)) return true
  return false
}

export function ChatPanel({
  messages, sending, loading,
  activeModel, thinkingElapsed, endRef, onSend, onVoiceStart, isRecording,
  cognitiveStatus,
}: Props) {
  const tts = useTTS()
  const spokenMsgsRef = useRef(new WeakSet<ChatMessage>())

  // Auto-speak new assistant messages
  useEffect(() => {
    for (const m of messages) {
      if (m.role === 'assistant' && !m._streaming && m.content && !spokenMsgsRef.current.has(m)) {
        spokenMsgsRef.current.add(m)
        tts.speak(m.content)
      }
    }
  }, [messages, tts.speak])

  // Wrap onSend to unlock audio during the user gesture
  const handleSend = useCallback((text: string) => {
    tts.initAudio()
    onSend(text)
  }, [onSend, tts.initAudio])

  // Also unlock audio on voice start (another user gesture)
  const handleVoiceStart = useCallback(() => {
    tts.initAudio()
    onVoiceStart?.()
  }, [onVoiceStart, tts.initAudio])

  const brainMessages = messages.filter(isBrainActivity)

  return (
    <div className="chat-panel">
      {/* Avatar — always present */}
      <div className="chat-avatar-area">
        <AvatarPresence
          cognitiveStatus={cognitiveStatus ?? null}
          sending={sending}
          hasMessages={messages.length > 0}
          onSend={handleSend}
          isSpeaking={tts.isSpeaking}
        />
      </div>

      {/* Brain activity feed — peek into the mind */}
      <div className="chat-messages-area">
        <div className="chat-messages-container">
          {brainMessages.map((m, i) => (
            <MessageBubble key={i} message={m} brainOnly />
          ))}

          {(loading || sending) && (
            <ThinkingIndicator
              activeModel={activeModel}
              elapsed={thinkingElapsed}
            />
          )}
          <div ref={endRef as React.LegacyRef<HTMLDivElement>} />
        </div>
      </div>

      {/* TTS volume controls */}
      <div className="tts-controls">
        <button
          onClick={tts.toggleMute}
          className={`tts-mute-btn${tts.muted ? ' muted' : ''}`}
          title={tts.muted ? 'Unmute voice' : 'Mute voice'}
        >
          {tts.muted ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <line x1="23" y1="9" x2="17" y2="15" />
              <line x1="17" y1="9" x2="23" y2="15" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            </svg>
          )}
        </button>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={tts.muted ? 0 : tts.volume}
          onChange={(e) => tts.setVolume(parseFloat(e.target.value))}
          className={`tts-volume-slider${tts.muted ? ' muted' : ''}`}
          title={`Volume: ${Math.round(tts.volume * 100)}%`}
        />
      </div>

      {/* Input area */}
      <ChatInput
        onSend={handleSend}
        disabled={sending}
        onVoiceStart={onVoiceStart ? handleVoiceStart : undefined}
        isRecording={isRecording}
      />
    </div>
  )
}
