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
      backdropFilter: 'blur(12px)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 24,
    }}>
      {/* Pulsing icon */}
      <div style={{
        width: 100, height: 100, borderRadius: '50%',
        background: isRecording ? 'rgba(196, 92, 92, 0.15)' : 'rgba(74, 122, 101, 0.15)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        animation: isRecording ? 'voicePulse 1.5s ease-in-out infinite' : 'none',
        border: `1px solid ${isRecording ? 'rgba(196, 92, 92, 0.3)' : 'rgba(74, 122, 101, 0.3)'}`,
      }}>
        {isTranscribing ? (
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" opacity="0.3" />
            <path d="M12 2a10 10 0 0 1 10 10" strokeDasharray="16" strokeDashoffset="0">
              <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
            </path>
          </svg>
        ) : (
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke={isRecording ? 'var(--accent-red)' : 'var(--primary)'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        )}
      </div>

      {/* Status text */}
      <div style={{
        fontSize: '0.95rem', fontWeight: 600, color: 'var(--text)',
        fontFamily: 'var(--font)', letterSpacing: '0.5px',
      }}>
        {isTranscribing ? 'Transcribing...' : isRecording ? 'Listening...' : 'Ready'}
      </div>

      {/* Recording indicator */}
      {isRecording && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--accent-red)',
            animation: 'voicePulse 1s ease-in-out infinite',
          }} />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font)', letterSpacing: '0.3px' }}>
            REC
          </span>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
        {isRecording && (
          <button onClick={onStop} style={{
            background: 'linear-gradient(175deg, var(--primary-light) 0%, var(--primary) 35%, var(--primary-dark) 100%)',
            border: 'none',
            color: 'var(--bg-primary)', fontFamily: 'var(--font)', fontSize: '0.8rem',
            fontWeight: 600, padding: '10px 28px', cursor: 'pointer',
            borderRadius: 'var(--radius-xs)', letterSpacing: '0.5px',
          }}>
            SEND
          </button>
        )}
        <button onClick={onCancel} style={{
          background: 'none', border: '1px solid rgba(255, 255, 255, 0.06)',
          color: 'var(--text-muted)', fontFamily: 'var(--font)', fontSize: '0.8rem',
          fontWeight: 500, padding: '10px 28px', cursor: 'pointer',
          borderRadius: 'var(--radius-xs)', letterSpacing: '0.3px',
        }}>
          CANCEL
        </button>
      </div>

      <style>{`
        @keyframes voicePulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.06); opacity: 0.7; }
        }
      `}</style>
    </div>
  )
}
