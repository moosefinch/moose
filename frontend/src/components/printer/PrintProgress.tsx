interface PrintProgressProps {
  progress: number
  layer?: number
  totalLayers?: number
  eta?: string
  fileName?: string
}

export function PrintProgress({ progress, layer, totalLayers, eta, fileName }: PrintProgressProps) {
  if (progress <= 0 && !fileName) {
    return (
      <div className="printer-card">
        <h3 className="printer-card-title">Print Progress</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No active print</p>
      </div>
    )
  }

  return (
    <div className="printer-card">
      <h3 className="printer-card-title">Print Progress</h3>
      {fileName && (
        <div className="print-progress-file">{fileName}</div>
      )}
      <div className="print-progress-bar-wrapper">
        <div className="print-progress-bar">
          <div
            className="print-progress-fill"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        <span className="print-progress-pct">{progress.toFixed(1)}%</span>
      </div>
      <div className="print-progress-details">
        {layer != null && totalLayers != null && (
          <span>Layer {layer} / {totalLayers}</span>
        )}
        {eta && <span>ETA: {eta}</span>}
      </div>
    </div>
  )
}
