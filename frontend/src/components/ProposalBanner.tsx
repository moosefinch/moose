import type { ImprovementProposal } from '../types'

interface Props {
  proposals: ImprovementProposal[]
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

const severityColors: Record<string, string> = {
  high: 'var(--accent-red)',
  medium: 'var(--accent-amber)',
  low: 'var(--text-muted)',
}

export function ProposalBanner({ proposals, onApprove, onReject }: Props) {
  if (proposals.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 16px' }}>
      {proposals.map(proposal => (
        <div key={proposal.id} style={{
          background: 'var(--bg-surface)',
          border: '1px solid rgba(6, 182, 212, 0.3)',
          borderRadius: 'var(--radius-sm)',
          padding: '12px 16px',
        }}>
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 8,
          }}>
            <span style={{
              fontSize: '0.7rem', fontWeight: 700, color: 'var(--primary)',
              textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              Improvement Proposal
            </span>
            <span style={{
              fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
              borderRadius: 4, textTransform: 'uppercase',
              background: `${severityColors[proposal.severity] || 'var(--text-muted)'}20`,
              color: severityColors[proposal.severity] || 'var(--text-muted)',
            }}>
              {proposal.severity}
            </span>
          </div>

          {/* Gap */}
          <div style={{ fontSize: '0.8rem', color: 'var(--text)', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Gap: </span>
            {proposal.gap_description}
          </div>

          {/* Solution */}
          <div style={{ fontSize: '0.8rem', color: 'var(--text)', marginBottom: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Solution: </span>
            {proposal.solution_summary || proposal.reasoning}
          </div>

          {/* Solution type badge */}
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 10 }}>
            Type: {proposal.solution_type.replace('_', ' ')} | Category: {proposal.category.replace('_', ' ')}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => onReject(proposal.id)}
              style={{
                background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)',
                color: 'var(--accent-red)', fontFamily: 'var(--font)', fontSize: '0.7rem',
                fontWeight: 600, padding: '4px 14px', cursor: 'pointer',
                borderRadius: 'var(--radius-xs)',
              }}
            >
              Reject
            </button>
            <button
              onClick={() => onApprove(proposal.id)}
              style={{
                background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)',
                color: 'var(--accent-green)', fontFamily: 'var(--font)', fontSize: '0.7rem',
                fontWeight: 600, padding: '4px 14px', cursor: 'pointer',
                borderRadius: 'var(--radius-xs)',
              }}
            >
              Approve
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
