import type { AgentEvent, AgentState, Briefing, AgentTask } from '../../types'

interface AgentActivityFeedProps {
  events: AgentEvent[]
  agents: AgentState[]
  briefings: Briefing[]
  tasks: AgentTask[]
}

// SVG icon components for event types — monochrome, crisp
const IconGear = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
)
const IconMail = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="4" width="20" height="16" rx="2" /><path d="M22 7l-10 7L2 7" />
  </svg>
)
const IconFlag = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" />
  </svg>
)
const IconSwap = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="17 1 21 5 17 9" /><path d="M3 11V9a4 4 0 0 1 4-4h14" />
    <polyline points="7 23 3 19 7 15" /><path d="M21 13v2a4 4 0 0 1-4 4H3" />
  </svg>
)
const IconPlay = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
)
const IconCheck = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)
const IconX = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)
const IconDot = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
    <circle cx="12" cy="12" r="3" />
  </svg>
)
const IconInfo = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
)

const EVENT_ICONS: Record<string, () => JSX.Element> = {
  tool_call: IconGear,
  message: IconMail,
  mission_update: IconFlag,
  model_swap: IconSwap,
  task_start: IconPlay,
  task_complete: IconCheck,
  error: IconX,
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}

export function AgentActivityFeed({ events, agents, briefings, tasks }: AgentActivityFeedProps) {
  const activeTasks = tasks.filter(t => t.status === 'running')
  const unreadBriefings = briefings.filter(b => !b.read)
  const recentEvents = events.slice(0, 20)

  return (
    <div className="dashboard-card activity-feed">
      <h3 className="dashboard-card-title">Activity</h3>

      {activeTasks.length > 0 && (
        <div className="feed-section">
          <div className="feed-section-label">Active Tasks</div>
          {activeTasks.map(t => (
            <div key={t.id} className="feed-item task-item">
              <span className="feed-icon" style={{ color: 'var(--accent-green)' }}><IconPlay /></span>
              <span className="feed-text">{t.description}</span>
            </div>
          ))}
        </div>
      )}

      {unreadBriefings.length > 0 && (
        <div className="feed-section">
          <div className="feed-section-label">Unread Briefings</div>
          {unreadBriefings.slice(0, 3).map(b => (
            <div key={b.id} className="feed-item briefing-item">
              <span className="feed-icon" style={{ color: 'var(--primary)' }}><IconInfo /></span>
              <span className="feed-text">{b.content.slice(0, 120)}{b.content.length > 120 ? '...' : ''}</span>
            </div>
          ))}
        </div>
      )}

      <div className="feed-section">
        <div className="feed-section-label">
          Agents
          <span className="feed-badge">{agents.filter(a => a.state === 'running').length} active</span>
        </div>
        <div className="agent-chips">
          {agents.map(a => (
            <span
              key={a.name}
              className="agent-chip"
              style={{
                borderColor: a.state === 'running' ? 'var(--accent-green)' :
                  a.state === 'waiting' ? 'var(--accent-amber)' :
                  a.state === 'error' ? 'var(--accent-red)' : 'var(--border)',
              }}
            >
              {a.name}
            </span>
          ))}
        </div>
      </div>

      <div className="feed-section">
        <div className="feed-section-label">Recent Events</div>
        <div className="feed-events-list">
          {recentEvents.length === 0 && (
            <div className="feed-empty">No events yet</div>
          )}
          {recentEvents.map(evt => {
            const Icon = EVENT_ICONS[evt.eventType] || IconDot
            return (
              <div key={evt.id} className="feed-item">
                <span className="feed-icon"><Icon /></span>
                <span className="feed-agent">{evt.agent}</span>
                <span className="feed-text">{evt.detail.slice(0, 80)}</span>
                <span className="feed-time">{relativeTime(evt.time)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
