import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../api'
import type { ChannelMessage } from '../types'

interface ChannelInfo {
  name: string
  allowed_agents: string[]
  message_count: number
  last_message: ChannelMessage | null
}

const AGENT_COLORS: Record<string, string> = {
  hermes: '#4fc3f7',
  ministral: '#81c784',
  coder: '#ffb74d',
  writer: '#ce93d8',
  math: '#90caf9',
  whiterabbit: '#ef5350',
  'whiterabbit-33b': '#ef9a9a',
  deepseek: '#ff7043',
  claude: '#a5d6a7',
  operator: '#06B6D4',
}

interface Props {
  messages: ChannelMessage[]
  onPostMessage?: (channel: string, content: string) => Promise<boolean>
}

export function ChannelsPanel({ messages, onPostMessage }: Props) {
  const [channels, setChannels] = useState<ChannelInfo[]>([])
  const [activeChannel, setActiveChannel] = useState<string>('#general')
  const [channelHistory, setChannelHistory] = useState<ChannelMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [posting, setPosting] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load channel list
  useEffect(() => {
    const load = async () => {
      try {
        const r = await apiFetch('/api/channels')
        if (r.ok) setChannels(await r.json())
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [])

  // Load channel history when switching
  useEffect(() => {
    const load = async () => {
      try {
        const name = activeChannel.replace('#', '')
        const r = await apiFetch(`/api/channels/${name}?limit=100`)
        if (r.ok) setChannelHistory(await r.json())
      } catch { /* ignore */ }
    }
    load()
  }, [activeChannel])

  // Append live messages for current channel
  const displayMessages = [
    ...channelHistory,
    ...messages.filter(m => m.channel === activeChannel && !channelHistory.find(h => h.id === m.id)),
  ]

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [displayMessages.length])

  const handlePost = async () => {
    if (!inputText.trim() || posting || !onPostMessage) return
    setPosting(true)
    await onPostMessage(activeChannel, inputText.trim())
    setInputText('')
    setPosting(false)
  }

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Channel list sidebar */}
      <div style={{
        width: '180px', borderRight: '1px solid var(--border)',
        overflowY: 'auto', flexShrink: 0, background: 'rgba(15, 23, 42, 0.4)',
      }}>
        <div style={{
          padding: '12px', borderBottom: '1px solid var(--border)',
          fontSize: '0.68rem', fontWeight: 600, color: 'var(--text-muted)',
          letterSpacing: '1px',
        }}>CHANNELS</div>
        {channels.map(ch => (
          <button
            key={ch.name}
            onClick={() => setActiveChannel(ch.name)}
            style={{
              display: 'block', width: '100%', padding: '10px 12px',
              textAlign: 'left', background: activeChannel === ch.name ? 'var(--primary-dim)' : 'transparent',
              border: 'none', borderBottom: '1px solid var(--border)',
              borderLeft: activeChannel === ch.name ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeChannel === ch.name ? 'var(--primary)' : 'var(--text-secondary)',
              cursor: 'pointer', fontFamily: 'var(--font)', fontSize: '0.78rem',
              fontWeight: activeChannel === ch.name ? 600 : 400,
              transition: 'all 0.15s',
            }}
          >
            <div>{ch.name}</div>
            <div style={{ fontSize: '0.6rem', opacity: 0.5, marginTop: '3px' }}>
              {ch.message_count} msgs{ch.allowed_agents ? ` / ${ch.allowed_agents.length} agents` : ''}
            </div>
          </button>
        ))}
      </div>

      {/* Message area + input */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div ref={scrollRef} style={{
          flex: 1, overflowY: 'auto', padding: '12px 16px',
          fontSize: '0.78rem', lineHeight: '1.6',
        }}>
          {displayMessages.length === 0 && (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px', fontSize: '0.82rem' }}>
              No messages in {activeChannel}
            </div>
          )}
          {displayMessages.map(msg => (
            <div key={msg.id} style={{
              marginBottom: '8px', padding: '6px 0',
              borderBottom: '1px solid rgba(148, 163, 184, 0.05)',
            }}>
              <span style={{
                color: AGENT_COLORS[msg.sender] || 'var(--text-muted)',
                fontWeight: 600, marginRight: '8px',
              }}>
                {msg.sender}
              </span>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.65rem', marginRight: '8px' }}>
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              <div style={{ color: 'var(--text-secondary)', marginTop: '2px', whiteSpace: 'pre-wrap' }}>
                {msg.content.length > 500 ? msg.content.slice(0, 500) + '...' : msg.content}
              </div>
            </div>
          ))}
        </div>

        {/* Message input */}
        {onPostMessage && (
          <div style={{
            display: 'flex', gap: '8px', padding: '10px 16px',
            borderTop: '1px solid var(--glass-border)',
            background: 'var(--glass)',
          }}>
            <input
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handlePost() } }}
              placeholder={`Message ${activeChannel}...`}
              disabled={posting}
              maxLength={2000}
              style={{
                flex: 1, border: '1px solid var(--border)',
                background: 'var(--bg-surface)', color: 'var(--text-primary)',
                fontFamily: 'var(--font)', fontSize: '0.82rem',
                padding: '8px 12px', borderRadius: 'var(--radius-xs)',
                outline: 'none',
              }}
            />
            <button
              onClick={handlePost}
              disabled={posting || !inputText.trim()}
              style={{
                background: inputText.trim() ? 'var(--primary-dim)' : 'var(--bg-surface)',
                border: '1px solid',
                borderColor: inputText.trim() ? 'rgba(6, 182, 212, 0.2)' : 'var(--border)',
                color: inputText.trim() ? 'var(--primary)' : 'var(--text-muted)',
                fontFamily: 'var(--font)', fontSize: '0.7rem', fontWeight: 600,
                padding: '8px 14px', cursor: inputText.trim() ? 'pointer' : 'default',
                borderRadius: 'var(--radius-xs)', letterSpacing: '0.5px',
              }}
            >POST</button>
          </div>
        )}
      </div>
    </div>
  )
}
