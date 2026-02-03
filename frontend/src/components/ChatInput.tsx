import { useState, useRef, useCallback, useEffect } from 'react'
import { useConfig } from '../contexts/ConfigContext'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  placeholder?: string
  onVoiceStart?: () => void
}

export function ChatInput({ onSend, disabled, placeholder, onVoiceStart }: Props) {
  const config = useConfig()
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const resize = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [])

  useEffect(() => { resize() }, [text, resize])

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, disabled, onSend])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  const active = text.trim() && !disabled

  return (
    <div style={{
      padding: '12px 24px 16px',
      borderTop: '1px solid var(--border)',
      background: 'var(--bg-secondary)',
    }}>
      <div style={{
        maxWidth: '720px', margin: '0 auto',
        display: 'flex', alignItems: 'flex-end', gap: '8px',
      }}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || `Message ${config.systemName}...`}
          disabled={disabled}
          maxLength={10000}
          rows={1}
          style={{
            flex: 1, resize: 'none', border: '1px solid var(--border)',
            background: 'var(--bg-surface)', color: 'var(--text)',
            fontFamily: 'var(--font)', fontSize: '0.9rem', lineHeight: '1.5',
            padding: '10px 14px', borderRadius: 'var(--radius-sm)',
            outline: 'none', transition: 'border-color 0.15s',
            minHeight: '42px', maxHeight: '160px',
          }}
          onFocus={(e) => e.currentTarget.style.borderColor = 'rgba(6, 182, 212, 0.4)'}
          onBlur={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
        />
        {onVoiceStart && (
          <button
            onClick={onVoiceStart}
            disabled={disabled}
            title="Voice input (Cmd+Shift+V)"
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              color: 'var(--text-muted)', fontFamily: 'var(--font)',
              fontSize: '1rem', padding: '8px 10px', cursor: disabled ? 'default' : 'pointer',
              borderRadius: 'var(--radius-sm)', transition: 'all 0.15s',
              minHeight: '42px', display: 'flex', alignItems: 'center',
            }}
          >{'\uD83C\uDF99'}</button>
        )}
        <button
          onClick={handleSend}
          disabled={!active}
          style={{
            background: active ? 'var(--primary)' : 'var(--bg-surface)',
            border: '1px solid',
            borderColor: active ? 'var(--primary)' : 'var(--border)',
            color: active ? '#121212' : 'var(--text-muted)',
            fontFamily: 'var(--font)', fontSize: '0.75rem', fontWeight: 600,
            padding: '10px 16px', cursor: active ? 'pointer' : 'default',
            borderRadius: 'var(--radius-sm)', letterSpacing: '0.5px',
            transition: 'all 0.15s', minHeight: '42px',
          }}
        >
          {disabled ? '...' : 'SEND'}
        </button>
      </div>
    </div>
  )
}
