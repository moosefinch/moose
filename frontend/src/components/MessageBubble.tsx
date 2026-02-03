import { useState } from 'react'
import type { ChatMessage } from '../types'
import { renderMarkdown } from '../lib/markdown'
import { ToolTrace } from './ToolTrace'
import { PlanTrace } from './PlanTrace'

const MODEL_COLORS: Record<string, string> = {
  hermes: 'hermes', ministral: 'ministral',
  whiterabbit: 'whiterabbit', claude: 'claude',
  deepseek: 'deepseek', system: 'system',
  china_intel: 'china_intel',
}

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
      <div style={{
        alignSelf: 'center', background: 'rgba(249, 115, 22, 0.06)',
        border: '1px solid rgba(249, 115, 22, 0.12)', color: 'var(--accent-orange)',
        borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', maxWidth: '100%',
        textAlign: 'center', padding: '10px 16px', animation: 'slideUp 0.2s ease-out',
      }}>
        {m.content}
      </div>
    )
  }

  // Proactive message — System initiated this unprompted
  if (m.proactive_category || m.role === 'proactive') {
    const category = m.proactive_category || 'observation'
    return (
      <div style={{
        maxWidth: '100%', padding: '12px 16px', fontSize: '0.85rem', lineHeight: 1.5,
        animation: 'slideUp 0.2s ease-out',
        background: 'rgba(6, 182, 212, 0.04)',
        borderLeft: '2px solid var(--primary)',
        borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
          <span style={{
            fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.5px',
            padding: '1px 6px', borderRadius: '3px',
            background: 'rgba(6, 182, 212, 0.1)', color: 'var(--primary)',
          }}>PROACTIVE</span>
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>{category}</span>
        </div>
        <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
      </div>
    )
  }

  const isUser = m.role === 'user'
  const isErr = m.error

  const badgeKey = MODEL_COLORS[m.model_key || ''] || ''
  const badgeColor = BADGE_COLORS[badgeKey]

  return (
    <div style={{
      maxWidth: '100%', padding: '14px 0', fontSize: '0.9rem', lineHeight: 1.5,
      animation: 'slideUp 0.2s ease-out', position: 'relative',
      background: isUser ? 'var(--bg-tertiary)' : 'transparent',
      borderRadius: isUser ? 'var(--radius-sm)' : '0',
      paddingLeft: isUser ? '16px' : '0',
      paddingRight: isUser ? '16px' : '0',
      color: isErr ? 'var(--accent-red)' : 'var(--text)',
      wordWrap: 'break-word',
    }}>
      {/* Model badge — simple colored text */}
      {!isUser && m.model_key && badgeColor && (
        <div style={{ marginBottom: '4px' }}>
          <span style={{
            fontSize: '0.7rem', fontWeight: 600, color: badgeColor,
            letterSpacing: '0.3px',
          }}>{m.model_label || m.model_key}</span>
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
        <div style={{
          position: 'absolute', top: '10px', right: '0',
          display: 'flex', gap: '4px', opacity: 0, transition: 'opacity 0.15s',
        }} className="msg-actions-hover">
          {m.audio_url && (
            <button onClick={() => {
              try {
                new Audio(m.audio_url!).play()
              } catch (e) { console.warn('Audio play failed:', e) }
            }} style={{
              background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font)', fontSize: '0.65rem', fontWeight: 500,
              padding: '3px 8px', cursor: 'pointer', borderRadius: 'var(--radius-xs)',
            }}>{'\uD83D\uDD0A'}</button>
          )}
          <button onClick={copyMsg} style={{
            background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            color: copied ? 'var(--accent-green)' : 'var(--text-secondary)',
            fontFamily: 'var(--font)', fontSize: '0.65rem', fontWeight: 500,
            padding: '3px 8px', cursor: 'pointer', borderRadius: 'var(--radius-xs)',
            borderColor: copied ? 'rgba(16, 185, 129, 0.3)' : 'var(--border)',
          }}>{copied ? 'COPIED' : 'COPY'}</button>
        </div>
      )}

      {/* Plan trace */}
      {!isUser && m.plan && <PlanTrace plan={m.plan} />}

      {/* Tool trace */}
      {!isUser && m.tool_calls && m.tool_calls.length > 0 && <ToolTrace calls={m.tool_calls} />}

      {/* Elapsed time */}
      {!isUser && !isErr && m.elapsed_seconds && m.elapsed_seconds > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '10px',
          paddingTop: '8px', borderTop: '1px solid var(--border)',
          fontSize: '0.7rem', color: 'var(--text-muted)',
        }}>
          <span>{m.elapsed_seconds}s</span>
        </div>
      )}

      <style>{`.msg-actions-hover { opacity: 0; } *:hover > .msg-actions-hover { opacity: 1; }`}</style>
    </div>
  )
}
