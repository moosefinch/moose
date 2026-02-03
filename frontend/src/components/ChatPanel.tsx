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
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      overflow: 'hidden', minWidth: 0,
    }}>
      {/* Messages area */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '20px 24px',
        display: 'flex', flexDirection: 'column', gap: '2px',
      }}>
        <div style={{ maxWidth: '720px', width: '100%', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {messages.length === 0 && !loading && !sending && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', flex: 1, padding: '80px 16px', textAlign: 'center',
            }}>
              <div style={{
                fontSize: '1.1rem', fontWeight: 700, letterSpacing: '4px',
                color: 'var(--text-muted)', marginBottom: '8px',
              }}>{config.systemName}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
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
