import type { ContentDraft } from '../types'

interface Props {
  draft: ContentDraft
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

const TYPE_COLORS: Record<string, string> = {
  blog_post: 'var(--primary)',
  twitter_post: 'rgb(29, 155, 240)',
  moltbook_post: 'var(--secondary)',
  social_post: 'rgb(0, 119, 181)',
  youtube_script: 'rgb(255, 0, 0)',
  landing_page: 'var(--accent-green)',
  email_newsletter: 'var(--text-muted)',
}

export function ContentApprovalCard({ draft, onApprove, onReject }: Props) {
  const bodyPreview = (draft.body || '').slice(0, 200) + ((draft.body || '').length > 200 ? '...' : '')
  const typeColor = TYPE_COLORS[draft.content_type] || 'var(--text-muted)'

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
      padding: '10px 12px', marginBottom: '8px',
      background: 'var(--bg-surface)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
        <span style={{
          fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px',
          borderRadius: '8px', border: `1px solid ${typeColor}`,
          color: typeColor,
        }}>
          {draft.content_type.replace(/_/g, ' ')}
        </span>
        {draft.platform && (
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
            {draft.platform}
          </span>
        )}
      </div>
      <div style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text)', marginBottom: '4px' }}>
        {draft.title}
      </div>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '8px', lineHeight: 1.4 }}>
        {bodyPreview}
      </div>
      <div style={{ display: 'flex', gap: '6px' }}>
        <button onClick={() => onApprove(draft.id)} style={{
          background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)',
          color: 'var(--accent-green)', fontSize: '0.7rem', fontWeight: 600,
          padding: '4px 12px', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          fontFamily: 'var(--font)',
        }}>Approve</button>
        <button onClick={() => onReject(draft.id)} style={{
          background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)',
          color: 'var(--accent-red)', fontSize: '0.7rem', fontWeight: 600,
          padding: '4px 12px', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          fontFamily: 'var(--font)',
        }}>Reject</button>
      </div>
    </div>
  )
}
