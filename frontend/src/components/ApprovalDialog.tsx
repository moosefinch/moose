import { useState } from 'react'
import { apiFetch } from '../api'

interface ApprovalRequest {
  id: string
  action: string
  description: string
  params: Record<string, unknown>
}

interface Props {
  approval: ApprovalRequest | null
  onResolved: () => void
}

export function ApprovalDialog({ approval, onResolved }: Props) {
  const [resolving, setResolving] = useState(false)
  const [confirmText, setConfirmText] = useState('')

  if (!approval) return null

  const isConfirmed = confirmText.toLowerCase() === 'approve'

  const resolve = async (approved: boolean) => {
    if (approved && !isConfirmed) return
    setResolving(true)
    try {
      await apiFetch(`/api/approve/${approval.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      })
    } catch (e) {
      console.error('[ApprovalDialog] Error:', e)
    }
    setResolving(false)
    setConfirmText('')
    onResolved()
  }

  const paramEntries = Object.entries(approval.params || {})

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }}>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', padding: 24, maxWidth: 480, width: '90%',
      }}>
        <h3 style={{ margin: '0 0 8px', fontSize: '0.9rem', color: 'var(--accent-red)' }}>
          Action Approval Required
        </h3>
        <p style={{ margin: '0 0 4px', fontSize: '0.8rem', fontWeight: 600 }}>
          {approval.action}
        </p>
        <p style={{ margin: '0 0 12px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {approval.description}
        </p>

        {/* Show parameters so user can verify what's being approved */}
        {paramEntries.length > 0 && (
          <div style={{
            margin: '0 0 12px', padding: '8px 10px',
            background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-xs)',
            border: '1px solid var(--border)', maxHeight: '120px', overflowY: 'auto',
          }}>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: 4, letterSpacing: '0.5px' }}>
              PARAMETERS
            </div>
            {paramEntries.map(([key, val]) => (
              <div key={key} style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: 2 }}>
                <span style={{ color: 'var(--text-muted)' }}>{key}:</span>{' '}
                <span style={{ wordBreak: 'break-all' }}>{typeof val === 'string' ? val : JSON.stringify(val)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Confirmation input */}
        <div style={{ margin: '0 0 12px' }}>
          <label style={{ fontSize: '0.65rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
            Type <strong style={{ color: 'var(--text-secondary)' }}>approve</strong> to confirm
          </label>
          <input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="approve"
            autoFocus
            style={{
              width: '100%', padding: '6px 10px', fontSize: '0.75rem',
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', borderRadius: 'var(--radius-xs)',
              fontFamily: 'var(--font)', outline: 'none', boxSizing: 'border-box',
            }}
            onKeyDown={(e) => { if (e.key === 'Enter' && isConfirmed) resolve(true) }}
          />
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button disabled={resolving} onClick={() => resolve(false)} style={{
            padding: '6px 16px', fontSize: '0.75rem', cursor: 'pointer',
            background: 'none', border: '1px solid var(--border)',
            color: 'var(--text-muted)', borderRadius: 'var(--radius-xs)',
          }}>Deny</button>
          <button disabled={resolving || !isConfirmed} onClick={() => resolve(true)} style={{
            padding: '6px 16px', fontSize: '0.75rem',
            cursor: isConfirmed ? 'pointer' : 'default',
            background: isConfirmed ? 'var(--primary)' : 'var(--bg-tertiary, #1e293b)',
            border: 'none',
            color: isConfirmed ? '#000' : 'var(--text-muted)',
            borderRadius: 'var(--radius-xs)', fontWeight: 600,
            opacity: isConfirmed ? 1 : 0.5,
          }}>Approve</button>
        </div>
      </div>
    </div>
  )
}
