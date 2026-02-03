import { useConfig } from '../contexts/ConfigContext'

interface Props {
  activeModel: string
  elapsed: number
}

export function ThinkingIndicator({ activeModel, elapsed }: Props) {
  const config = useConfig()

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '10px',
      padding: '14px 0', animation: 'slideUp 0.2s ease-out',
    }}>
      <div style={{ display: 'flex', gap: '4px' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: '5px', height: '5px', borderRadius: '50%',
            background: 'var(--text-muted)',
            animation: `dotPulse 1.4s ease-in-out infinite`,
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
      </div>
      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
        {config.systemName} is thinking
      </span>
      {activeModel && (
        <span style={{
          fontSize: '0.7rem', fontWeight: 600, color: 'var(--primary)',
        }}>{activeModel}</span>
      )}
      {elapsed > 0 && (
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{elapsed}s</span>
      )}
    </div>
  )
}
