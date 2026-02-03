import type { AgentState, CognitiveStatus } from '../../types'

interface AmbientIndicatorProps {
  cognitiveStatus: CognitiveStatus | null
  agents: AgentState[]
  expanded: boolean
  onToggle: () => void
}

const STATE_CONFIG: Record<string, { color: string; label: string }> = {
  idle: { color: 'var(--text-muted)', label: 'Idle' },
  observing: { color: 'var(--primary)', label: 'Observing' },
  thinking: { color: 'var(--secondary)', label: 'Thinking' },
  acting: { color: 'var(--accent-green)', label: 'Acting' },
}

function getAIState(cs: CognitiveStatus | null, agents: AgentState[]): string {
  if (!cs) return 'idle'
  const active = agents.filter(a => a.state === 'running')
  if (active.length > 0) return 'acting'
  if (cs.phase === 'observe' || cs.phase === 'orient') return 'observing'
  if (cs.phase === 'decide') return 'thinking'
  if (cs.phase === 'act') return 'acting'
  return 'idle'
}

export function AmbientIndicator({ cognitiveStatus, agents, expanded, onToggle }: AmbientIndicatorProps) {
  const state = getAIState(cognitiveStatus, agents)
  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle
  const activeAgents = agents.filter(a => a.state === 'running')

  return (
    <div className={`ambient-indicator ${state !== 'idle' ? 'active' : ''}`}>
      <button className="ambient-pill" onClick={onToggle}>
        <span className={`ambient-dot ${state !== 'idle' ? 'pulse' : ''}`} style={{ background: cfg.color }} />
        <span className="ambient-label">{cfg.label}</span>
        {cognitiveStatus && (
          <span className="ambient-cycle">C{cognitiveStatus.cycle}</span>
        )}
      </button>

      {expanded && (
        <div className="ambient-dropdown">
          <div className="ambient-dropdown-header">AI Status</div>
          <div className="ambient-dropdown-row">
            <span>Phase</span>
            <span style={{ textTransform: 'capitalize' }}>{cognitiveStatus?.phase ?? 'idle'}</span>
          </div>
          <div className="ambient-dropdown-row">
            <span>Observations</span>
            <span>{cognitiveStatus?.observations ?? 0}</span>
          </div>
          <div className="ambient-dropdown-row">
            <span>Thoughts</span>
            <span>{cognitiveStatus?.thoughts ?? 0}</span>
          </div>
          {activeAgents.length > 0 && (
            <>
              <div className="ambient-dropdown-header">Active Agents</div>
              {activeAgents.map(a => (
                <div key={a.name} className="ambient-dropdown-row">
                  <span>{a.name}</span>
                  <span style={{ color: 'var(--accent-green)' }}>running</span>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}
