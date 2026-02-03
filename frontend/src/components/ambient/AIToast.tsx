interface AIToastProps {
  toasts: { id: string; content: string; type?: string }[]
  onDismiss: (id: string) => void
}

export function AIToast({ toasts, onDismiss }: AIToastProps) {
  if (toasts.length === 0) return null

  return (
    <div className="ai-toast-container">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`ai-toast ${toast.type === 'ai' ? 'ai-toast-insight' : ''}`}
          onClick={() => onDismiss(toast.id)}
        >
          {toast.type === 'ai' && <span className="ai-toast-icon">&#10024;</span>}
          <span className="ai-toast-content">{toast.content}</span>
        </div>
      ))}
    </div>
  )
}
