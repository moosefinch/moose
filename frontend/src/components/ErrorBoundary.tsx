import { Component } from 'react'
import type { ReactNode, ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] Component error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          height: '100%', padding: '16px', color: 'var(--text-muted)', fontSize: '0.75rem',
          background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-xs)',
        }}>
          <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--accent-red, #ef4444)' }}>Component Error</div>
          <div style={{ fontSize: '0.65rem', opacity: 0.7, textAlign: 'center', maxWidth: '200px', wordBreak: 'break-word' }}>
            {this.state.error?.message || 'An unexpected error occurred'}
          </div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              marginTop: '8px', padding: '4px 12px', fontSize: '0.6rem', fontWeight: 600,
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              color: 'var(--text-secondary)', cursor: 'pointer', borderRadius: 'var(--radius-xs)',
              fontFamily: 'var(--font)',
            }}
          >RETRY</button>
        </div>
      )
    }
    return this.props.children
  }
}
