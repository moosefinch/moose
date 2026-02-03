import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'

interface PrinterStatus {
  state?: string
  nozzle_temp?: number
  nozzle_target?: number
  bed_temp?: number
  bed_target?: number
  progress?: number
  current_file?: string
}

export function PrinterStatusWidget() {
  const [status, setStatus] = useState<PrinterStatus | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await apiFetch('/api/printer/status')
        if (r.ok) {
          setStatus(await r.json())
          setError(false)
        } else {
          setError(true)
        }
      } catch {
        setError(true)
      }
    }
    poll()
    const id = setInterval(poll, 10000)
    return () => clearInterval(id)
  }, [])

  const stateColor = (s?: string) => {
    if (s === 'printing') return 'var(--accent-green)'
    if (s === 'error' || s === 'offline') return 'var(--accent-red)'
    if (s === 'paused') return 'var(--accent-amber)'
    return 'var(--text-muted)'
  }

  return (
    <div className="dashboard-card">
      <h3 className="dashboard-card-title">Printer</h3>
      {error || !status ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          {error ? 'Printer not connected' : 'Loading...'}
        </p>
      ) : (
        <div className="printer-widget-content">
          <div className="printer-widget-row">
            <span className="printer-widget-dot" style={{ background: stateColor(status.state) }} />
            <span style={{ textTransform: 'capitalize' }}>{status.state || 'Unknown'}</span>
          </div>
          {status.nozzle_temp != null && (
            <div className="printer-widget-row">
              <span className="printer-widget-label">Nozzle</span>
              <span>{status.nozzle_temp}°C / {status.nozzle_target ?? '--'}°C</span>
            </div>
          )}
          {status.bed_temp != null && (
            <div className="printer-widget-row">
              <span className="printer-widget-label">Bed</span>
              <span>{status.bed_temp}°C / {status.bed_target ?? '--'}°C</span>
            </div>
          )}
          {status.progress != null && status.progress > 0 && (
            <div className="printer-widget-progress">
              <div className="printer-widget-bar">
                <div className="printer-widget-bar-fill" style={{ width: `${status.progress}%` }} />
              </div>
              <span className="printer-widget-pct">{status.progress.toFixed(0)}%</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
