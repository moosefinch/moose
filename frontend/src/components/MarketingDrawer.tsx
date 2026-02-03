import { useEffect, useState } from 'react'
import { EmailApprovalCard } from './EmailApprovalCard'
import { ContentApprovalCard } from './ContentApprovalCard'
import type { PendingEmail, ContentDraft, MarketingStats } from '../types'

type Tab = 'emails' | 'content' | 'stats'

interface Props {
  open: boolean
  onClose: () => void
  pendingEmails: PendingEmail[]
  pendingContent: ContentDraft[]
  stats: MarketingStats | null
  onApproveEmail: (id: string) => void
  onRejectEmail: (id: string) => void
  onEditEmail: (id: string) => void
  onApproveContent: (id: string) => void
  onRejectContent: (id: string) => void
  embedded?: boolean
}

export function MarketingDrawer({
  open, onClose,
  pendingEmails, pendingContent, stats,
  onApproveEmail, onRejectEmail, onEditEmail,
  onApproveContent, onRejectContent,
  embedded,
}: Props) {
  const [tab, setTab] = useState<Tab>('emails')

  useEffect(() => {
    if (!open || embedded) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose, embedded])

  if (!open) return null

  const tabStyle = (t: Tab) => ({
    background: tab === t ? 'rgba(6, 182, 212, 0.1)' : 'none',
    border: tab === t ? '1px solid rgba(6, 182, 212, 0.3)' : '1px solid var(--border)',
    color: tab === t ? 'var(--primary)' : 'var(--text-muted)',
    fontSize: '0.7rem', fontWeight: 600 as const,
    padding: '3px 10px', borderRadius: 'var(--radius-xs)',
    cursor: 'pointer' as const, fontFamily: 'var(--font)',
  })

  const content = (
    <>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0,
      }}>
        <span style={{
          fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)',
          letterSpacing: '1px',
        }}>MARKETING</span>
          <div style={{ display: 'flex', gap: '4px', marginLeft: '8px' }}>
            <button onClick={() => setTab('emails')} style={tabStyle('emails')}>
              Emails{pendingEmails.length > 0 ? ` (${pendingEmails.length})` : ''}
            </button>
            <button onClick={() => setTab('content')} style={tabStyle('content')}>
              Content{pendingContent.length > 0 ? ` (${pendingContent.length})` : ''}
            </button>
            <button onClick={() => setTab('stats')} style={tabStyle('stats')}>
              Stats
            </button>
          </div>
          {!embedded && <button onClick={onClose} style={{
            marginLeft: 'auto', background: 'none', border: '1px solid var(--border)',
            color: 'var(--text-muted)', fontFamily: 'var(--font)',
            fontSize: '0.7rem', padding: '4px 8px',
            cursor: 'pointer', borderRadius: 'var(--radius-xs)',
          }}>ESC</button>}
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
          {tab === 'emails' && (
            pendingEmails.length === 0 ? (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0' }}>
                No pending emails
              </div>
            ) : (
              pendingEmails.map(e => (
                <EmailApprovalCard
                  key={e.id} email={e}
                  onApprove={onApproveEmail}
                  onReject={onRejectEmail}
                  onEdit={onEditEmail}
                />
              ))
            )
          )}

          {tab === 'content' && (
            pendingContent.length === 0 ? (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0' }}>
                No pending content
              </div>
            ) : (
              pendingContent.map(d => (
                <ContentApprovalCard
                  key={d.id} draft={d}
                  onApprove={onApproveContent}
                  onReject={onRejectContent}
                />
              ))
            )
          )}

          {tab === 'stats' && stats && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text)' }}>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--primary)' }}>Emails</div>
                {Object.entries(stats.emails).map(([status, count]) => (
                  <div key={status} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', color: 'var(--text-muted)' }}>
                    <span>{status}</span><span style={{ fontVariantNumeric: 'tabular-nums' }}>{count}</span>
                  </div>
                ))}
                {Object.keys(stats.emails).length === 0 && (
                  <div style={{ color: 'var(--text-muted)' }}>No emails yet</div>
                )}
              </div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--primary)' }}>Content</div>
                {Object.entries(stats.content).map(([status, count]) => (
                  <div key={status} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', color: 'var(--text-muted)' }}>
                    <span>{status}</span><span style={{ fontVariantNumeric: 'tabular-nums' }}>{count}</span>
                  </div>
                ))}
                {Object.keys(stats.content).length === 0 && (
                  <div style={{ color: 'var(--text-muted)' }}>No content yet</div>
                )}
              </div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--primary)' }}>Overview</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', color: 'var(--text-muted)' }}>
                  <span>Personas</span><span>{stats.personas}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', color: 'var(--text-muted)' }}>
                  <span>Prospects</span><span>{stats.prospects}</span>
                </div>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--primary)' }}>Cadences</div>
                {stats.cadences.map(c => (
                  <div key={c.loop_type} style={{
                    display: 'flex', justifyContent: 'space-between', padding: '2px 0', color: 'var(--text-muted)',
                  }}>
                    <span>{c.loop_type.replace(/_/g, ' ')}</span>
                    <span style={{
                      color: c.enabled ? 'var(--accent-green)' : 'var(--text-muted)',
                      fontWeight: 600,
                    }}>{c.enabled ? 'ON' : 'OFF'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'stats' && !stats && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0' }}>
              Loading stats...
            </div>
          )}
        </div>
    </>
  )

  if (embedded) {
    return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>{content}</div>
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer-right" style={{ width: 480 }}>{content}</div>
    </>
  )
}
