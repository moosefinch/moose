import { useState } from 'react'
import type { ToolCall } from '../types'

interface Props {
  calls: ToolCall[]
}

export function ToolTrace({ calls }: Props) {
  const [open, setOpen] = useState(false)
  if (!calls || calls.length === 0) return null

  return (
    <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border)' }}>
      <button onClick={() => setOpen(!open)} style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        color: 'var(--text-secondary)', fontFamily: 'var(--font)',
        fontSize: '0.7rem', fontWeight: 500, padding: '4px 10px',
        cursor: 'pointer', borderRadius: 'var(--radius-xs)', transition: 'all 0.15s',
      }}>
        {open ? '\u25BC' : '\u25B6'} {calls.length} tool{calls.length > 1 ? 's' : ''} used
      </button>
      {open && (
        <div style={{ marginTop: '8px', fontSize: '0.75rem' }}>
          {calls.map((tc, i) => (
            <div key={i} style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderLeft: '3px solid var(--secondary-dim)',
              padding: '8px 10px', marginBottom: '4px', lineHeight: 1.5,
              borderRadius: '0 var(--radius-xs) var(--radius-xs) 0',
            }}>
              <span style={{ color: 'var(--secondary)', fontWeight: 600 }}>{tc.tool}</span>
              <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>
                ({Object.entries(tc.args || {}).map(([k, v]) => {
                  const val = typeof v === 'string' && v.length > 60 ? v.slice(0, 60) + '...' : String(v)
                  return `${k}: ${val}`
                }).join(', ')})
              </span>
              {tc.result && (
                <div style={{
                  color: 'var(--text-secondary)', marginTop: '4px',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: '0.7rem',
                }}>
                  {tc.result.length > 300 ? tc.result.slice(0, 300) + '...' : tc.result}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
