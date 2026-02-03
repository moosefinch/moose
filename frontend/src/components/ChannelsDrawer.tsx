import { useEffect } from 'react'
import { ChannelsPanel } from './ChannelsPanel'
import type { ChannelMessage } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  messages: ChannelMessage[]
  onPostMessage?: (channel: string, content: string) => Promise<boolean>
}

export function ChannelsDrawer({ open, onClose, messages, onPostMessage }: Props) {
  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer-right">
        <div style={{
          padding: '10px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0,
        }}>
          <span style={{
            fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)',
            letterSpacing: '1px',
          }}>CHANNELS</span>
          <button onClick={onClose} style={{
            marginLeft: 'auto', background: 'none', border: '1px solid var(--border)',
            color: 'var(--text-muted)', fontFamily: 'var(--font)',
            fontSize: '0.7rem', padding: '4px 8px',
            cursor: 'pointer', borderRadius: 'var(--radius-xs)',
          }}>ESC</button>
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <ChannelsPanel messages={messages} onPostMessage={onPostMessage} />
        </div>
      </div>
    </>
  )
}
