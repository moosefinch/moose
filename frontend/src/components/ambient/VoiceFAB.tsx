interface VoiceFABProps {
  isRecording: boolean
  onStart: () => void
  onStop: () => void
}

export function VoiceFAB({ isRecording, onStart, onStop }: VoiceFABProps) {
  return (
    <button
      className={`voice-fab ${isRecording ? 'recording' : ''}`}
      onClick={isRecording ? onStop : onStart}
      title={isRecording ? 'Stop recording (Cmd+Shift+V)' : 'Start voice input (Cmd+Shift+V)'}
    >
      {isRecording ? (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
        </svg>
      ) : (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      )}
    </button>
  )
}
