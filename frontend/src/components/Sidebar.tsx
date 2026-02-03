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

  return (
    <div className={`sidebar${open ? '' : ' collapsed'}`}>
      {/* Conversations section */}
      <div style={{
        padding: '12px 12px 8px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <span style={{
          fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-muted)',
          letterSpacing: '1px',
        }}>CONVERSATIONS</span>
        <button onClick={onNewConversation} style={{
          background: 'var(--primary-dim)', border: '1px solid rgba(6, 182, 212, 0.2)',
          color: 'var(--primary)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 600, padding: '3px 10px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }}>+ New</button>
      </div>

      {/* Conversation list */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {conversations.length === 0 && (
          <div style={{
            color: 'var(--text-muted)', textAlign: 'center',
            padding: '20px 12px', fontSize: '0.75rem',
          }}>No conversations yet</div>
        )}
        {conversations.map(c => (
          <div
            key={c.id}
            onClick={() => onSelectConversation(c.id)}
            style={{
              padding: '8px 12px', cursor: 'pointer',
              background: activeConvoId === c.id ? 'var(--primary-dim)' : 'transparent',
              borderLeft: activeConvoId === c.id ? '2px solid var(--primary)' : '2px solid transparent',
              borderBottom: '1px solid var(--border)',
              transition: 'background 0.1s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{
                fontSize: '0.8rem', fontWeight: activeConvoId === c.id ? 600 : 400,
                color: activeConvoId === c.id ? 'var(--text)' : 'var(--text-secondary)',
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{c.title || 'New conversation'}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onDeleteConversation(c.id) }}
                style={{
                  background: 'none', border: 'none', color: 'var(--text-muted)',
                  cursor: 'pointer', fontSize: '0.7rem', padding: '2px 4px',
                  opacity: 0.4, transition: 'opacity 0.1s', flexShrink: 0,
                }}
                onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                onMouseLeave={(e) => e.currentTarget.style.opacity = '0.4'}
              >{'\u2715'}</button>
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '2px',
            }}>
              <span>{formatTime(c.updated_at)}</span>
              {c.message_count !== undefined && <span>{c.message_count} msgs</span>}
            </div>
            {c.first_message && (
              <div style={{
                fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '2px',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{c.first_message}</div>
            )}
          </div>
        ))}
      </div>

      {/* Agents section — collapsible */}
      <div style={{ borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <button
          onClick={() => setAgentsExpanded(!agentsExpanded)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', gap: '6px',
            padding: '8px 12px', background: 'none', border: 'none',
            color: 'var(--text-muted)', cursor: 'pointer', fontFamily: 'var(--font)',
            fontSize: '0.7rem', fontWeight: 600, letterSpacing: '1px', textAlign: 'left',
          }}
        >
          <span>{agentsExpanded ? '\u25BC' : '\u25B6'}</span>
          <span>AGENTS</span>
          {runningAgents > 0 && (
            <span style={{
              fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px',
              borderRadius: '8px', background: 'var(--primary-dim)', color: 'var(--primary)',
              marginLeft: '4px',
            }}>{runningAgents}</span>
          )}
        </button>
        {agentsExpanded && agents.length > 0 && (
          <div style={{ padding: '0 12px 8px', maxHeight: '150px', overflowY: 'auto' }}>
            {agents.map((a, i) => (
              <div key={a.id || i} style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '4px 0', fontSize: '0.75rem',
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: a.state === 'running' ? 'var(--primary)' :
                    a.state === 'error' ? 'var(--accent-red)' :
                    a.state === 'completed' ? 'var(--accent-green)' : 'var(--text-muted)',
                }} />
                <span style={{ color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.name}
                </span>
                <span style={{
                  fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase',
                }}>{a.state}</span>
              </div>
            ))}
          </div>
        )}
        {agentsExpanded && agents.length === 0 && (
          <div style={{ padding: '4px 12px 8px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            No agents active
          </div>
        )}
      </div>

      {/* Cognitive loop status */}
      {cognitiveStatus && (
        <div style={{
          borderTop: '1px solid var(--border)', padding: '6px 12px',
          display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: cognitiveStatus.phase !== 'idle' ? 'var(--primary)' : 'var(--text-muted)',
            animation: cognitiveStatus.phase !== 'idle' ? 'pulse 1.5s ease-in-out infinite' : 'none',
          }} />
          <span style={{
            fontSize: '0.65rem', color: 'var(--text-muted)', flex: 1,
          }}>
            {cognitiveStatus.phase !== 'idle'
              ? `${cognitiveStatus.phase.charAt(0).toUpperCase() + cognitiveStatus.phase.slice(1)}...`
              : 'Idle'}
          </span>
          <span style={{
            fontSize: '0.6rem', color: 'var(--text-muted)',
          }}>#{cognitiveStatus.cycle}</span>
          <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }`}</style>
        </div>
      )}

      {/* Quick actions footer */}
      <div style={{
        borderTop: '1px solid var(--border)', padding: '8px 12px',
        display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0,
      }}>
        <button onClick={onOpenMarketing} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 500, padding: '3px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
          transition: 'color 0.1s',
          position: 'relative',
        }} title="Marketing (Cmd+P)">
          {'\u2318'}P
          {pendingMarketing > 0 && (
            <span style={{
              position: 'absolute', top: -4, right: -4,
              fontSize: '0.6rem', fontWeight: 700, padding: '0 4px',
              borderRadius: '6px', background: 'rgba(245, 158, 11, 0.2)', color: 'var(--accent-amber)',
              lineHeight: '14px', minWidth: '14px', textAlign: 'center',
            }}>{pendingMarketing}</span>
          )}
        </button>
        <button onClick={onOpenChannels} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 500, padding: '3px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }} title="Channels (Cmd+J)">#</button>
        <button onClick={onOpenMemory} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 500, padding: '3px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }} title="Memory (Cmd+M)">{'\u2318'}M</button>
        <button onClick={onOpenScheduling} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 500, padding: '3px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }} title="Scheduling (Cmd+Shift+S)">{'\u23F0'}</button>
        <button onClick={onOpenPlugins} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)',
          fontSize: '0.7rem', fontWeight: 500, padding: '3px 8px',
          cursor: 'pointer', borderRadius: 'var(--radius-xs)',
        }} title="Plugins">{'\u{1F9E9}'}</button>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: connected ? 'var(--accent-green)' : apiUp ? 'var(--primary)' : 'var(--text-muted)',
          }} />
          <span style={{
            fontSize: '0.65rem', fontWeight: 600, letterSpacing: '0.5px',
            color: connected ? 'var(--accent-green)' : apiUp ? 'var(--primary)' : 'var(--text-muted)',
          }}>
            {connected ? 'LIVE' : apiUp ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>
    </div>
  )
}
