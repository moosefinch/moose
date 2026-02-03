import type { PrinterStatus } from '../../hooks/usePrinter'

interface PrinterDashboardProps {
  status: PrinterStatus | null
}

export function PrinterDashboard({ status }: PrinterDashboardProps) {
  const stateColor = (s?: string) => {
    if (s === 'printing') return 'var(--accent-green)'
    if (s === 'error' || s === 'offline') return 'var(--accent-red)'
    if (s === 'paused') return 'var(--accent-amber)'
    if (s === 'idle' || s === 'ready') return 'var(--primary)'
    return 'var(--text-muted)'
  }

  return (
    <div className="printer-card">
      <h3 className="printer-card-title">Printer Status</h3>
      {!status || !status.connected ? (
        <div className="printer-offline">
          <span className="printer-offline-dot" />
          <span>Printer not connected</span>
        </div>
      ) : (
        <div className="printer-status-info">
          <div className="printer-status-row">
            <span className="printer-state-dot" style={{ background: stateColor(status.state) }} />
            <span className="printer-state-label" style={{ textTransform: 'capitalize' }}>
              {status.state || 'Unknown'}
            </span>
          </div>
          {status.current_file && (
            <div className="printer-status-row">
              <span className="printer-label">File</span>
              <span className="printer-value">{status.current_file}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
