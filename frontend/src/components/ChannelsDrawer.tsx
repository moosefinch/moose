import { useEffect } from 'react'
import { ChannelsPanel } from './ChannelsPanel'
import type { ChannelMessage } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  messages: ChannelMessage[]
  onPostMessage?: (channel: string, content: string) => Promise<boolean>
  embedded?: boolean
}

export function ChannelsDrawer({ open, onClose, messages, onPostMessage, embedded }: Props) {
  useEffect(() => {
    if (!open || embedded) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose, embedded])

  if (!open) return null

  const content = (
    <>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0,
      }}>
        <span style={{
          fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)',
          letterSpacing: '1px',
        }}>CHANNELS</span>
        {!embedded && <button onClick={onClose} style={{
          marginLeft: 'auto', background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', padding: '4px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }}>ESC</button>}
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <ChannelsPanel messages={messages} onPostMessage={onPostMessage} />
      </div>
    </>
  )

  if (embedded) {
    return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>{content}</div>
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer-right">{content}</div>
    </>
  )
}
