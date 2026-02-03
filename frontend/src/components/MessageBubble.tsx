import { useState } from 'react'
import type { ChatMessage } from '../types'
import { renderMarkdown } from '../lib/markdown'
import { ToolTrace } from './ToolTrace'
import { PlanTrace } from './PlanTrace'

const BADGE_COLORS: Record<string, string> = {
  hermes: '#10B981',
  ministral: '#A78BFA',
  whiterabbit: '#F87171',
  claude: '#FB923C',
  deepseek: '#F87171',
  system: 'var(--primary)',
  china_intel: '#F87171',
}

interface Props {
  message: ChatMessage
}

export function MessageBubble({ message }: Props) {
  const [copied, setCopied] = useState(false)
  const m = message

  const copyMsg = () => {
    navigator.clipboard.writeText(m.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  if (m.role === 'notification') {
    return (
      <div className="message-notification">
        {m.content}
      </div>
    )
  }

  // Proactive message — System initiated this unprompted
  if (m.proactive_category || m.role === 'proactive') {
    const category = m.proactive_category || 'observation'
    return (
      <div className="message-proactive">
        <div className="message-proactive-header">
          <span className="message-proactive-badge">PROACTIVE</span>
          <span className="message-proactive-category">{category}</span>
        </div>
        <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
      </div>
    )
  }

  const isUser = m.role === 'user'
  const isErr = m.error

  const badgeColor = BADGE_COLORS[m.model_key || '']

  return (
    <div className={`message-bubble ${isUser ? 'message-bubble-user' : ''} ${isErr ? 'message-bubble-error' : ''}`}>
      {/* Model badge — simple colored text */}
      {!isUser && m.model_key && badgeColor && (
        <div className="message-model-badge" style={{ color: badgeColor }}>
          {m.model_label || m.model_key}
        </div>
      )}

      {/* Content */}
      {!isUser && !isErr ? (
        <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
      ) : (
        <div style={{ whiteSpace: isUser ? 'pre-wrap' : undefined }}>{m.content}</div>
      )}

      {/* Copy + Speaker actions */}
      {!isUser && !isErr && (
        <div className="message-actions">
          {m.audio_url && (
            <button
              onClick={() => {
                try {
                  new Audio(m.audio_url!).play()
                } catch (e) { console.warn('Audio play failed:', e) }
              }}
              className="message-action-btn"
            >
              {'\uD83D\uDD0A'}
            </button>
          )}
          <button
            onClick={copyMsg}
            className={`message-action-btn ${copied ? 'copied' : ''}`}
          >
            {copied ? 'COPIED' : 'COPY'}
          </button>
        </div>
      )}

      {/* Plan trace */}
      {!isUser && m.plan && <PlanTrace plan={m.plan} />}

      {/* Tool trace */}
      {!isUser && m.tool_calls && m.tool_calls.length > 0 && <ToolTrace calls={m.tool_calls} />}

      {/* Elapsed time */}
      {!isUser && !isErr && m.elapsed_seconds && m.elapsed_seconds > 0 && (
        <div className="message-footer">
          <span>{m.elapsed_seconds}s</span>
        </div>
      )}
    </div>
  )
}
