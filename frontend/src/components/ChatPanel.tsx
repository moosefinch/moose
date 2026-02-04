import { MessageBubble } from './MessageBubble'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ChatInput } from './ChatInput'
import { AvatarPresence } from './AvatarPresence'
import { useConfig } from '../contexts/ConfigContext'
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
  cognitiveStatus?: CognitiveStatus | null
}

export function ChatPanel({
  messages, sending, loading,
  activeModel, thinkingElapsed, endRef, onSend, onVoiceStart,
  cognitiveStatus,
}: Props) {
  const config = useConfig()

  return (
    <div className="chat-panel">
      {/* Messages area */}
      <div className="chat-messages-area">
        <div className="chat-messages-container">
          {messages.length === 0 && !loading && !sending && (
            <div className="chat-empty-state">
              <AvatarPresence
                cognitiveStatus={cognitiveStatus ?? null}
                sending={sending}
                hasMessages={false}
                onSend={onSend}
              />
              <div className="chat-empty-logo">{config.systemName}</div>
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
