import { useState, useRef, useCallback, useEffect } from 'react'
import { useConfig } from '../contexts/ConfigContext'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  placeholder?: string
  onVoiceStart?: () => void
  isRecording?: boolean
}

export function ChatInput({ onSend, disabled, placeholder, onVoiceStart, isRecording }: Props) {
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
    <div className="chat-input-wrapper">
      <div className="chat-input-container">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || `Message ${config.systemName}...`}
          disabled={disabled}
          maxLength={10000}
          rows={1}
          className="chat-textarea"
        />
        {onVoiceStart && (
          <button
            onClick={onVoiceStart}
            disabled={disabled}
            title="Voice input (Cmd+Shift+V)"
            className={`chat-voice-btn${isRecording ? ' recording' : ''}`}
          >
            {isRecording ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </button>
        )}
        <button
          onClick={handleSend}
          disabled={!active}
          className={`chat-send-btn ${active ? 'active' : ''}`}
        >
          {disabled ? '...' : 'SEND'}
        </button>
      </div>
    </div>
  )
}
