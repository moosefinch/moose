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
            className="chat-voice-btn"
          >
            {'\uD83C\uDF99'}
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
