import type { ImprovementProposal } from '../types'

interface Props {
  proposals: ImprovementProposal[]
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onClose: () => void
}

const statusColors: Record<string, string> = {
  pending: 'var(--accent-amber)',
  approved: 'var(--primary)',
  executing: 'var(--primary)',
  completed: 'var(--accent-green)',
  failed: 'var(--accent-red)',
  rejected: 'var(--text-muted)',
}

const severityColors: Record<string, string> = {
  high: 'var(--accent-red)',
  medium: 'var(--accent-amber)',
  low: 'var(--text-muted)',
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleString()
}

export function ProposalsHistoryPanel({ proposals, onApprove, onReject, onClose }: Props) {
  const pending = proposals.filter(p => p.status === 'pending')
  const rest = proposals.filter(p => p.status !== 'pending')

  const btnStyle: React.CSSProperties = {
    background: 'var(--primary-dim)', border: '1px solid rgba(6, 182, 212, 0.2)',
    color: 'var(--primary)', fontFamily: 'var(--font)', fontSize: '0.7rem',
    fontWeight: 600, padding: '4px 12px', cursor: 'pointer',
    borderRadius: 'var(--radius-xs)',
  }

  const successBtnStyle: React.CSSProperties = {
    ...btnStyle, background: 'rgba(34, 197, 94, 0.1)',
    borderColor: 'rgba(34, 197, 94, 0.2)', color: 'var(--accent-green)',
  }

  const dangerBtnStyle: React.CSSProperties = {
    ...btnStyle, background: 'rgba(239, 68, 68, 0.1)',
    borderColor: 'rgba(239, 68, 68, 0.2)', color: 'var(--accent-red)',
  }

  return (
    <div style={{
      position: 'relative', width: '100%', height: '100%',
      background: 'var(--bg-secondary)', display: 'flex', flexDirection: 'column',
      flex: 1, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text)' }}>
          Improvement Proposals ({proposals.length})
        </span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)',
          cursor: 'pointer', fontSize: '1rem',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {proposals.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
            No proposals yet. The system will create proposals when it detects capability gaps.
          </div>
        )}

        {/* Pending proposals first */}
        {pending.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              fontSize: '0.7rem', fontWeight: 700, color: 'var(--accent-amber)',
              textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em',
            }}>
              Pending Approval ({pending.length})
            </div>
            {pending.map(p => (
              <ProposalCard key={p.id} proposal={p} onApprove={onApprove} onReject={onReject}
                successBtnStyle={successBtnStyle} dangerBtnStyle={dangerBtnStyle} />
            ))}
          </div>
        )}

        {/* History */}
        {rest.length > 0 && (
          <div>
            <div style={{
              fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em',
            }}>
              History
            </div>
            {rest.map(p => (
              <ProposalCard key={p.id} proposal={p} onApprove={onApprove} onReject={onReject}
                successBtnStyle={successBtnStyle} dangerBtnStyle={dangerBtnStyle} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ProposalCard({ proposal: p, onApprove, onReject, successBtnStyle, dangerBtnStyle }: {
  proposal: ImprovementProposal
  onApprove: (id: string) => void
  onReject: (id: string) => void
  successBtnStyle: React.CSSProperties
  dangerBtnStyle: React.CSSProperties
}) {
  return (
    <div style={{
      padding: '10px 12px', marginBottom: 8,
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: statusColors[p.status] || 'var(--text-muted)',
        }} />
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
          {p.gap_description}
        </span>
        <span style={{
          fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
          borderRadius: 4, textTransform: 'uppercase',
          background: `${statusColors[p.status] || 'var(--text-muted)'}20`,
          color: statusColors[p.status] || 'var(--text-muted)',
        }}>{p.status}</span>
        <span style={{
          fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
          borderRadius: 4, textTransform: 'uppercase',
          background: `${severityColors[p.severity] || 'var(--text-muted)'}20`,
          color: severityColors[p.severity] || 'var(--text-muted)',
        }}>{p.severity}</span>
      </div>

      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>
        {p.solution_type.replace('_', ' ')} — {p.solution_summary || p.reasoning}
      </div>

      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: 6 }}>
        Created: {formatTime(p.created_at)}
        {p.completed_at && ` — Completed: ${formatTime(p.completed_at)}`}
      </div>

      {/* Execution log (collapsed for non-pending) */}
      {p.execution_log.length > 0 && p.status !== 'pending' && (
        <div style={{
          fontSize: '0.65rem', color: 'var(--text-muted)',
          background: 'var(--bg-secondary)', borderRadius: 'var(--radius-xs)',
          padding: '6px 8px', marginBottom: 6, maxHeight: 80, overflowY: 'auto',
        }}>
          {p.execution_log.map((entry, i) => (
            <div key={i}>{entry.message}</div>
          ))}
        </div>
      )}

      {p.error && (
        <div style={{ fontSize: '0.7rem', color: 'var(--accent-red)', marginBottom: 6 }}>
          Error: {p.error}
        </div>
      )}

      {p.result && p.status === 'completed' && (
        <div style={{ fontSize: '0.7rem', color: 'var(--accent-green)', marginBottom: 6 }}>
          {p.result}
        </div>
      )}

      {p.status === 'pending' && (
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => onReject(p.id)} style={dangerBtnStyle}>Reject</button>
          <button onClick={() => onApprove(p.id)} style={successBtnStyle}>Approve</button>
        </div>
      )}
    </div>
  )
}
