import { useNavigation, type Page } from '../../contexts/NavigationContext'
import type { CognitiveStatus } from '../../types'
import MooseAvatar, { type AvatarState } from '../MooseAvatar'

const TABS: { id: Page; label: string; shortcut: string }[] = [
  { id: 'dashboard', label: 'Dashboard', shortcut: '1' },
  { id: 'viewport', label: 'Viewport', shortcut: '2' },
  { id: 'printer', label: 'Printer', shortcut: '3' },
  { id: 'more', label: 'More', shortcut: '4' },
]

interface TabBarProps {
  connected: boolean
  apiUp: boolean
  cognitiveStatus: CognitiveStatus | null
}

// Map cognitive phases to avatar states
function phaseToAvatarState(phase: string): AvatarState {
  switch (phase) {
    case 'observe':
    case 'orient':
      return 'thinking'
    case 'decide':
      return 'thinking'
    case 'act':
      return 'talking'
    default:
      return 'idle'
  }
}

export function TabBar({ connected, apiUp, cognitiveStatus }: TabBarProps) {
  const { page, setPage } = useNavigation()

  const phase = cognitiveStatus?.phase ?? 'idle'
  const avatarState = phaseToAvatarState(phase)

  const phaseColors: Record<string, string> = {
    idle: 'var(--text-muted)',
    observe: 'var(--primary)',
    orient: 'var(--accent-amber)',
    decide: 'var(--secondary)',
    act: 'var(--accent-green)',
  }

  return (
    <nav className="tab-bar">
      {/* Moose Avatar Logo */}
      <div className="tab-bar-logo">
        <MooseAvatar
          state={avatarState}
          size={36}
          className="tab-bar-avatar"
        />
        <span className="tab-bar-brand">Moose</span>
      </div>

      <div className="tab-bar-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-bar-tab ${page === tab.id ? 'active' : ''}`}
            onClick={() => setPage(tab.id)}
            title={`${tab.label} (Cmd+${tab.shortcut})`}
          >
            {tab.label}
            <span className="tab-shortcut">{tab.shortcut}</span>
          </button>
        ))}
      </div>

      <div className="tab-bar-status">
        <div
          className={`ai-status-pill ${phase !== 'idle' ? 'active' : ''}`}
          title={`AI: ${phase} | Cycle: ${cognitiveStatus?.cycle ?? 0}`}
        >
          <span
            className="ai-status-dot"
            style={{ background: phaseColors[phase] || phaseColors.idle }}
          />
          <span className="ai-status-label">{phase}</span>
        </div>

        <div className="connection-indicators">
          <span
            className="conn-dot"
            style={{ background: connected ? 'var(--accent-green)' : 'var(--accent-red)' }}
            title={connected ? 'WebSocket connected' : 'WebSocket disconnected'}
          />
          <span
            className="conn-dot"
            style={{ background: apiUp ? 'var(--accent-green)' : 'var(--accent-red)' }}
            title={apiUp ? 'API online' : 'API offline'}
          />
        </div>
      </div>
    </nav>
  )
}
