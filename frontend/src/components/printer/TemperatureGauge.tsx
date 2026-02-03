interface TemperatureGaugeProps {
  nozzleTemp: number
  nozzleTarget: number
  bedTemp: number
  bedTarget: number
}

function TempBar({ label, current, target }: { label: string; current: number; target: number }) {
  const pct = target > 0 ? Math.min((current / target) * 100, 100) : 0
  const atTarget = target > 0 && Math.abs(current - target) < 3
  const color = atTarget ? 'var(--accent-green)' : current > 0 ? 'var(--accent-amber)' : 'var(--text-muted)'

  return (
    <div className="temp-gauge">
      <div className="temp-gauge-header">
        <span className="temp-gauge-label">{label}</span>
        <span className="temp-gauge-value" style={{ color }}>
          {current.toFixed(0)}°C
          {target > 0 && <span className="temp-gauge-target"> / {target}°C</span>}
        </span>
      </div>
      <div className="temp-gauge-bar">
        <div
          className="temp-gauge-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

export function TemperatureGauge({ nozzleTemp, nozzleTarget, bedTemp, bedTarget }: TemperatureGaugeProps) {
  return (
    <div className="printer-card">
      <h3 className="printer-card-title">Temperatures</h3>
      <TempBar label="Nozzle" current={nozzleTemp} target={nozzleTarget} />
      <TempBar label="Bed" current={bedTemp} target={bedTarget} />
    </div>
  )
}
