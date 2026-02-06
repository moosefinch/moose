import { useState } from 'react'
import type { Briefing, AgentState, CognitiveStatus } from '../types'

interface Props {
  open: boolean
  onToggle: () => void
  briefings: Briefing[]
  onMarkBriefingRead: (id: string) => void
  onMarkAllRead: () => void
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


// Inline SVG icons — crisp, no emoji
const ChevronDown = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.5 3.5L5 6.5L7.5 3.5" />
  </svg>
)
const ChevronRight = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3.5 2L6.5 5L3.5 8" />
  </svg>
)

export function Sidebar({
  open, onToggle,
  briefings, onMarkBriefingRead, onMarkAllRead,
  agents, connected, apiUp,
  pendingMarketing, onOpenMarketing, onOpenChannels, onOpenMemory, onOpenScheduling, onOpenPlugins,
  cognitiveStatus,
}: Props) {
  const [agentsExpanded, setAgentsExpanded] = useState(false)

  const runningAgents = agents.filter(a => a.state === 'running').length
  const unreadCount = briefings.filter(b => !b.read).length

  return (
    <div className={`sidebar${open ? '' : ' collapsed'}`}>
      {/* Briefings section */}
      <div className="sidebar-section-header">
        <span className="sidebar-section-title">BRIEFINGS</span>
        {unreadCount > 0 && (
          <button onClick={onMarkAllRead} className="sidebar-new-btn">
            Mark Read
          </button>
        )}
      </div>

      {/* Briefing list */}
      <div className="sidebar-list">
        {briefings.length === 0 && (
          <div className="sidebar-empty">No briefings yet</div>
        )}
        {briefings.map(b => (
          <div
            key={b.id}
            onClick={() => { if (!b.read) onMarkBriefingRead(b.id) }}
            className={`sidebar-item${!b.read ? ' active' : ''}`}
          >
            <div className="sidebar-item-header">
              <span className="sidebar-item-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {!b.read && (
                  <span
                    style={{
                      width: 6, height: 6, borderRadius: '50%',
                      background: 'var(--primary)', flexShrink: 0,
                    }}
                  />
                )}
                {b.content.length > 80 ? b.content.slice(0, 80) + '...' : b.content}
              </span>
            </div>
            <div className="sidebar-item-meta">
              <span>{formatTime(b.created_at)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Agents section — collapsible */}
      <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.04)', flexShrink: 0 }}>
        <button
          onClick={() => setAgentsExpanded(!agentsExpanded)}
          className="sidebar-collapse-header"
        >
          <span style={{ display: 'flex', alignItems: 'center' }}>
            {agentsExpanded ? <ChevronDown /> : <ChevronRight />}
          </span>
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
        <button onClick={onOpenMarketing} className="sidebar-action-btn" title="Marketing">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
          {pendingMarketing > 0 && (
            <span className="sidebar-action-badge">{pendingMarketing}</span>
          )}
        </button>
        <button onClick={onOpenChannels} className="sidebar-action-btn" title="Channels">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="9" x2="20" y2="9" /><line x1="4" y1="15" x2="20" y2="15" />
            <line x1="10" y1="3" x2="8" y2="21" /><line x1="16" y1="3" x2="14" y2="21" />
          </svg>
        </button>
        <button onClick={onOpenMemory} className="sidebar-action-btn" title="Memory">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3" />
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
          </svg>
        </button>
        <button onClick={onOpenScheduling} className="sidebar-action-btn" title="Scheduling">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
        </button>
        <button onClick={onOpenPlugins} className="sidebar-action-btn" title="Plugins">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
          </svg>
        </button>
      </div>
    </div>
  )
}
