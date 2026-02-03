interface Props {
  open: boolean
  isRecording: boolean
  isTranscribing: boolean
  onStop: () => void
  onCancel: () => void
}

export function VoiceModeOverlay({ open, isRecording, isTranscribing, onStop, onCancel }: Props) {
  if (!open) return null

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0, 0, 0, 0.85)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 24,
    }}>
      {/* Pulsing mic icon */}
      <div style={{
        width: 100, height: 100, borderRadius: '50%',
        background: isRecording ? 'rgba(239, 68, 68, 0.2)' : 'rgba(6, 182, 212, 0.2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        animation: isRecording ? 'voicePulse 1.5s ease-in-out infinite' : 'none',
        border: `2px solid ${isRecording ? 'rgba(239, 68, 68, 0.5)' : 'rgba(6, 182, 212, 0.5)'}`,
      }}>
        <span style={{ fontSize: '2.5rem' }}>
          {isTranscribing ? '\u23F3' : '\uD83C\uDF99'}
        </span>
      </div>

      {/* Status text */}
      <div style={{
        fontSize: '1.1rem', fontWeight: 600, color: 'var(--text)',
        fontFamily: 'var(--font)',
      }}>
        {isTranscribing ? 'Transcribing...' : isRecording ? 'Listening...' : 'Ready'}
      </div>

      {/* Recording indicator */}
      {isRecording && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent-red)',
            animation: 'voicePulse 1s ease-in-out infinite',
          }} />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--font)' }}>
            Recording
          </span>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 16, marginTop: 16 }}>
        {isRecording && (
          <button onClick={onStop} style={{
            background: 'var(--primary)', border: 'none',
            color: '#121212', fontFamily: 'var(--font)', fontSize: '0.85rem',
            fontWeight: 600, padding: '10px 24px', cursor: 'pointer',
            borderRadius: 'var(--radius-sm)',
          }}>
            Send
          </button>
        )}
        <button onClick={onCancel} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)', fontSize: '0.85rem',
          fontWeight: 500, padding: '10px 24px', cursor: 'pointer',
          borderRadius: 'var(--radius-sm)',
        }}>
          Cancel
        </button>
      </div>

      <style>{`
        @keyframes voicePulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.7; }
        }
      `}</style>
    </div>
  )
}
