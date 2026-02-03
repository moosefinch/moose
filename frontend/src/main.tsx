import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import { ConfigProvider } from './contexts/ConfigContext'
import './styles/global.css'
import './styles/layout.css'
import 'highlight.js/styles/github-dark.css'

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <pre style={{
          position: 'fixed', inset: 0, zIndex: 99999,
          background: '#0a0a0a', color: '#ff6666', padding: 24,
          fontSize: 14, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
          overflow: 'auto',
        }}>
          {`REACT ERROR:\n\n${this.state.error.message}\n\n${this.state.error.stack || ''}`}
        </pre>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ConfigProvider>
        <App />
      </ConfigProvider>
    </ErrorBoundary>
  </React.StrictMode>
)
