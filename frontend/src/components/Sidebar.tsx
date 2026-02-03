import { useState } from 'react'
import type { Conversation, AgentState, CognitiveStatus } from '../types'

interface Props {
  open: boolean
  onToggle: () => void
  conversations: Conversation[]
  activeConvoId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onDeleteConversation: (id: string) => void
  agents: AgentState[]
  connected: boolean
  apiUp: boolean
  pendingMarketing: number
  onOpenMarketing: () => void
  onOpenChannels: () => void
  onOpenMemory: () => void
  onOpenScheduling: () => void
  onOpenPlugins: () => void
  cognitiveStatus?: CognitiveStatus | null
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago'
  return d.toLocaleDateString()
}

function getAgentDotColor(state: string): string {
  switch (state) {
    case 'running': return 'var(--primary)'
    case 'error': return 'var(--accent-red)'
    case 'completed': return 'var(--accent-green)'
    default: return 'var(--text-muted)'
  }
}

function getStatusInfo(connected: boolean, apiUp: boolean) {
  if (connected) return { color: 'var(--accent-green)', label: 'LIVE' }
  if (apiUp) return { color: 'var(--primary)', label: 'ONLINE' }
  return { color: 'var(--text-muted)', label: 'OFFLINE' }
}

export function Sidebar({
  open, onToggle,
  conversations, activeConvoId,
  onSelectConversation, onNewConversation, onDeleteConversation,
  agents, connected, apiUp,
  pendingMarketing, onOpenMarketing, onOpenChannels, onOpenMemory, onOpenScheduling, onOpenPlugins,
  cognitiveStatus,
}: Props) {
  const [agentsExpanded, setAgentsExpanded] = useState(false)

  const runningAgents = agents.filter(a => a.state === 'running').length
  const status = getStatusInfo(connected, apiUp)

  return (
    <div className={`sidebar${open ? '' : ' collapsed'}`}>
      {/* Conversations section */}
      <div className="sidebar-section-header">
        <span className="sidebar-section-title">CONVERSATIONS</span>
        <button onClick={onNewConversation} className="sidebar-new-btn">
          + New
        </button>
      </div>

      {/* Conversation list */}
      <div className="sidebar-list">
        {conversations.length === 0 && (
          <div className="sidebar-empty">No conversations yet</div>
        )}
        {conversations.map(c => (
          <div
            key={c.id}
            onClick={() => onSelectConversation(c.id)}
            className={`sidebar-item ${activeConvoId === c.id ? 'active' : ''}`}
          >
            <div className="sidebar-item-header">
              <span className="sidebar-item-title">{c.title || 'New conversation'}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onDeleteConversation(c.id) }}
                className="sidebar-item-delete"
              >
                {'\u2715'}
              </button>
            </div>
            <div className="sidebar-item-meta">
              <span>{formatTime(c.updated_at)}</span>
              {c.message_count !== undefined && <span>{c.message_count} msgs</span>}
            </div>
            {c.first_message && (
              <div className="sidebar-item-preview">{c.first_message}</div>
            )}
          </div>
        ))}
      </div>

      {/* Agents section — collapsible */}
      <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.03)', flexShrink: 0 }}>
        <button
          onClick={() => setAgentsExpanded(!agentsExpanded)}
          className="sidebar-collapse-header"
        >
          <span>{agentsExpanded ? '\u25BC' : '\u25B6'}</span>
          <span>AGENTS</span>
          {runningAgents > 0 && (
            <span className="sidebar-collapse-badge">{runningAgents}</span>
          )}
        </button>
        {agentsExpanded && agents.length > 0 && (
          <div className="sidebar-collapse-content">
            {agents.map((a, i) => (
              <div key={a.id || i} className="sidebar-agent-item">
                <span
                  className="sidebar-agent-dot"
                  style={{ background: getAgentDotColor(a.state) }}
                />
                <span className="sidebar-agent-name">{a.name}</span>
                <span className="sidebar-agent-state">{a.state}</span>
              </div>
            ))}
          </div>
        )}
        {agentsExpanded && agents.length === 0 && (
          <div className="sidebar-collapse-content">
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>No agents active</span>
          </div>
        )}
      </div>

      {/* Cognitive loop status */}
      {cognitiveStatus && (
        <div className="sidebar-cognitive-status">
          <span
            className={`sidebar-cognitive-dot ${cognitiveStatus.phase !== 'idle' ? 'active' : ''}`}
            style={{ background: cognitiveStatus.phase !== 'idle' ? 'var(--primary)' : 'var(--text-muted)' }}
          />
          <span className="sidebar-cognitive-phase">
            {cognitiveStatus.phase !== 'idle'
              ? `${cognitiveStatus.phase.charAt(0).toUpperCase() + cognitiveStatus.phase.slice(1)}...`
              : 'Idle'}
          </span>
          <span className="sidebar-cognitive-cycle">#{cognitiveStatus.cycle}</span>
        </div>
      )}

      {/* Quick actions footer */}
      <div className="sidebar-footer">
        <button onClick={onOpenMarketing} className="sidebar-action-btn" title="Marketing (Cmd+P)">
          {'\u2318'}P
          {pendingMarketing > 0 && (
            <span className="sidebar-action-badge">{pendingMarketing}</span>
          )}
        </button>
        <button onClick={onOpenChannels} className="sidebar-action-btn" title="Channels (Cmd+J)">#</button>
        <button onClick={onOpenMemory} className="sidebar-action-btn" title="Memory (Cmd+M)">{'\u2318'}M</button>
        <button onClick={onOpenScheduling} className="sidebar-action-btn" title="Scheduling (Cmd+Shift+S)">{'\u23F0'}</button>
        <button onClick={onOpenPlugins} className="sidebar-action-btn" title="Plugins">{'\u{1F9E9}'}</button>

        <div className="sidebar-status">
          <span className="sidebar-status-dot" style={{ background: status.color }} />
          <span className="sidebar-status-label" style={{ color: status.color }}>{status.label}</span>
        </div>
      </div>
    </div>
  )
}
