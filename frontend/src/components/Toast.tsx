interface ToastItem {
  id: string
  content: string
}

interface Props {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

export function Toast({ toasts, onDismiss }: Props) {
  if (!toasts || toasts.length === 0) return null
  return (
    <div style={{
      position: 'fixed', top: '48px', right: '16px', zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: '8px',
    }}>
      {toasts.map(t => (
        <div key={t.id} onClick={() => onDismiss(t.id)} style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border)',
          padding: '10px 14px', borderRadius: 'var(--radius-sm)',
          color: 'var(--text)', fontSize: '0.8rem',
          maxWidth: '340px', animation: 'toastSlide 0.3s ease-out',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)', cursor: 'pointer',
        }}>
          <div style={{ fontWeight: 600, color: 'var(--primary)', marginBottom: '4px', fontSize: '0.7rem', letterSpacing: '0.5px' }}>NOTIFICATION</div>
          <div>{(t.content || '').slice(0, 120)}{(t.content || '').length > 120 ? '...' : ''}</div>
        </div>
      ))}
    </div>
  )
}
