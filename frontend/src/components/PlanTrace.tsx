import { useState } from 'react'
import type { PlanData } from '../types'

const PLAN_MODEL_COLORS: Record<string, { bg: string; color: string }> = {
  ministral: { bg: 'var(--secondary-dim)', color: '#A78BFA' },
  whiterabbit: { bg: 'rgba(239, 68, 68, 0.12)', color: '#F87171' },
  hermes: { bg: 'rgba(16, 185, 129, 0.12)', color: '#10B981' },
  china_intel: { bg: 'rgba(239, 68, 68, 0.12)', color: '#F87171' },
  claude: { bg: 'rgba(249, 115, 22, 0.12)', color: '#FB923C' },
}

interface Props {
  plan: PlanData
}

export function PlanTrace({ plan }: Props) {
  const [open, setOpen] = useState(false)
  if (!plan || !plan.tasks || plan.tasks.length === 0) return null

  return (
    <div style={{ marginTop: '10px' }}>
      <button onClick={() => setOpen(!open)} style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        color: 'var(--text-secondary)', fontFamily: 'var(--font)',
        fontSize: '0.7rem', fontWeight: 500, padding: '4px 10px',
        cursor: 'pointer', borderRadius: 'var(--radius-xs)', transition: 'all 0.15s',
      }}>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
          {open ? <path d="M2.5 3.5L5 6.5L7.5 3.5" /> : <path d="M3.5 2L6.5 5L3.5 8" />}
        </svg>
        Plan: {plan.tasks.length} task{plan.tasks.length > 1 ? 's' : ''}{plan.synthesized ? ' + synthesis' : ''}
        {plan.complexity && <span style={{ color: 'var(--text-muted)', fontSize: '0.6rem', letterSpacing: '0.5px', marginLeft: '4px' }}>[{plan.complexity}]</span>}
      </button>
      {open && (
        <div style={{ marginTop: '8px', fontSize: '0.75rem' }}>
          {plan.summary && <div style={{ color: 'var(--accent-green)', marginBottom: '6px', fontWeight: 500 }}>{plan.summary}</div>}
          {plan.tasks.map((t, i) => {
            const mc = PLAN_MODEL_COLORS[t.model] || { bg: 'var(--bg-surface)', color: 'var(--text-muted)' }
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '6px 10px', marginBottom: '3px',
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderLeft: '3px solid var(--primary-dim)',
                borderRadius: '0 var(--radius-xs) var(--radius-xs) 0',
              }}>
                <span style={{
                  fontSize: '0.6rem', fontWeight: 600, padding: '2px 8px',
                  borderRadius: '10px', letterSpacing: '0.5px',
                  background: mc.bg, color: mc.color,
                }}>{t.model}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{t.task}</span>
                {t.depends_on && t.depends_on.length > 0 && (
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.6rem', marginLeft: 'auto' }}>dep: {t.depends_on.join(',')}</span>
                )}
              </div>
            )
          })}
          {plan.synthesized && (
            <div style={{ color: 'var(--accent-green)', fontSize: '0.65rem', marginTop: '4px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 }}>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 2v6h6" />
              </svg>
              HERMES SYNTHESIS
            </div>
          )}
        </div>
      )}
    </div>
  )
}
