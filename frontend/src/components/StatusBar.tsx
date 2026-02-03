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
        cursor: 'pointer', fontSize: '0.85rem', padding: '2px 4px',
        fontFamily: 'var(--font)', lineHeight: 1,
      }} title="Toggle sidebar (Cmd+\\)">
        {sidebarOpen ? '\u2630' : '\u2630'}
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
