import { MessageBubble } from './MessageBubble'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ChatInput } from './ChatInput'
import { useConfig } from '../contexts/ConfigContext'
import type { ChatMessage } from '../types'

interface Props {
  messages: ChatMessage[]
  sending: boolean
  loading: boolean
  activeModel: string
  thinkingElapsed: number
  endRef: React.RefObject<HTMLDivElement | null>
  onSend: (text: string) => void
  onVoiceStart?: () => void
}

export function ChatPanel({
  messages, sending, loading,
  activeModel, thinkingElapsed, endRef, onSend, onVoiceStart,
}: Props) {
  const config = useConfig()

  return (
    <div className="chat-panel">
      {/* Messages area */}
      <div className="chat-messages-area">
        <div className="chat-messages-container">
          {messages.length === 0 && !loading && !sending && (
            <div className="chat-empty-state">
              <div className="chat-empty-logo">{config.systemName}</div>
              <div className="chat-empty-hint">
                Send a message to begin.
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
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

      {/* Input area */}
      <ChatInput
        onSend={onSend}
        disabled={sending}
        onVoiceStart={onVoiceStart}
      />
    </div>
  )
}
