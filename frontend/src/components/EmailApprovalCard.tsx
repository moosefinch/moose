import type { PendingEmail } from '../types'

interface Props {
  email: PendingEmail
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onEdit: (id: string) => void
}

export function EmailApprovalCard({ email, onApprove, onReject, onEdit }: Props) {
  const bodyPreview = (email.body || '').slice(0, 200) + ((email.body || '').length > 200 ? '...' : '')

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
      padding: '10px 12px', marginBottom: '8px',
      background: 'var(--bg-surface)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text)' }}>
          {email.contact_name || 'Unknown'}
        </span>
        {email.prospect_company && (
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            @ {email.prospect_company}
          </span>
        )}
      </div>
      <div style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--primary)', marginBottom: '4px' }}>
        {email.subject || '(no subject)'}
      </div>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '8px', lineHeight: 1.4 }}>
        {bodyPreview}
      </div>
      <div style={{ display: 'flex', gap: '6px' }}>
        <button onClick={() => onApprove(email.id)} style={{
          background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)',
          color: 'var(--accent-green)', fontSize: '0.7rem', fontWeight: 600,
          padding: '4px 12px', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          fontFamily: 'var(--font)',
        }}>Approve</button>
        <button onClick={() => onEdit(email.id)} style={{
          background: 'rgba(6, 182, 212, 0.08)', border: '1px solid rgba(6, 182, 212, 0.2)',
          color: 'var(--primary)', fontSize: '0.7rem', fontWeight: 600,
          padding: '4px 12px', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          fontFamily: 'var(--font)',
        }}>Edit</button>
        <button onClick={() => onReject(email.id)} style={{
          background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)',
          color: 'var(--accent-red)', fontSize: '0.7rem', fontWeight: 600,
          padding: '4px 12px', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          fontFamily: 'var(--font)',
        }}>Reject</button>
      </div>
    </div>
  )
}
