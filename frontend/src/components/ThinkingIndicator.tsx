import { useConfig } from '../contexts/ConfigContext'

interface Props {
  activeModel: string
  elapsed: number
}

export function ThinkingIndicator({ activeModel, elapsed }: Props) {
  const config = useConfig()

  return (
    <div className="thinking-indicator">
      <div className="thinking-dots">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="thinking-dot"
            style={{ animationDelay: `${i * 0.2}s` }}
          />
        ))}
      </div>
      <div className="thinking-info">
        <span className="thinking-model">
          {config.systemName} is thinking{activeModel && ` · ${activeModel}`}
        </span>
        {elapsed > 0 && (
          <span className="thinking-elapsed">{elapsed}s</span>
        )}
      </div>
    </div>
  )
}
