import { useConfig } from '../contexts/ConfigContext'

interface Props {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  activeConvoTitle?: string
  connected: boolean
  apiUp: boolean
}

export function StatusBar({ sidebarOpen, onToggleSidebar, activeConvoTitle, connected, apiUp }: Props) {
  const config = useConfig()
  const statusText = connected ? 'LIVE' : apiUp ? 'ONLINE' : 'OFFLINE'

  return (
    <div className="status-bar">
      {/* Sidebar toggle */}
      <button onClick={onToggleSidebar} style={{
        background: 'none', border: 'none', color: 'var(--text-muted)',
        cursor: 'pointer', padding: '2px 4px', lineHeight: 1,
        display: 'flex', alignItems: 'center',
      }} title="Toggle sidebar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Wordmark */}
      <span style={{
        fontSize: '0.7rem', fontWeight: 700, letterSpacing: '3px',
        color: 'var(--text-muted)',
      }}>{config.systemName}</span>

      {/* Active conversation title */}
      {activeConvoTitle && (
        <span style={{
          fontSize: '0.75rem', color: 'var(--text-secondary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          flex: 1, textAlign: 'center',
        }}>{activeConvoTitle}</span>
      )}
      {!activeConvoTitle && <span style={{ flex: 1 }} />}

      {/* Connection status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
        <span style={{
          width: 6, height: 6, borderRadius: '50%',
          background: connected ? 'var(--accent-green)' : apiUp ? 'var(--primary)' : 'var(--text-muted)',
        }} />
        <span style={{
          fontSize: '0.65rem', fontWeight: 600, letterSpacing: '0.5px',
          color: connected ? 'var(--accent-green)' : apiUp ? 'var(--primary)' : 'var(--text-muted)',
        }}>{statusText}</span>
      </div>
    </div>
  )
}
