import type { AgentEvent, AgentState, Briefing, AgentTask } from '../../types'

interface AgentActivityFeedProps {
  events: AgentEvent[]
  agents: AgentState[]
  briefings: Briefing[]
  tasks: AgentTask[]
}

const EVENT_ICONS: Record<string, string> = {
  tool_call: '\u2699',
  message: '\u2709',
  mission_update: '\u2691',
  model_swap: '\u21C4',
  task_start: '\u25B6',
  task_complete: '\u2713',
  error: '\u2717',
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
              <span className="feed-icon" style={{ color: 'var(--accent-green)' }}>&#9654;</span>
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
              <span className="feed-icon" style={{ color: 'var(--primary)' }}>&#9432;</span>
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
          {recentEvents.map(evt => (
            <div key={evt.id} className="feed-item">
              <span className="feed-icon">{EVENT_ICONS[evt.eventType] || '\u2022'}</span>
              <span className="feed-agent">{evt.agent}</span>
              <span className="feed-text">{evt.detail.slice(0, 80)}</span>
              <span className="feed-time">{relativeTime(evt.time)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
