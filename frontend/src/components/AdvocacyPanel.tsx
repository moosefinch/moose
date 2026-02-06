import { useState } from 'react'
import type { AdvocacyGoal, AdvocacyPattern, AdvocacyStatus } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  status: AdvocacyStatus | null
  goals: AdvocacyGoal[]
  unconfirmedGoals: AdvocacyGoal[]
  patterns: AdvocacyPattern[]
  onCreateGoal: (data: { text: string; category?: string; priority?: number }) => void
  onUpdateGoal: (id: string, data: { status?: string; priority?: number }) => void
  onConfirmGoal: (id: string) => void
  onRejectGoal: (id: string) => void
  onRecordEvidence: (id: string, data: { type?: string; description: string }) => void
  onDismissPattern: (id: string) => void
  onStartOnboarding: () => void
  onRespondOnboarding: (text: string) => Promise<{ next_prompt?: string; stage?: string; complete?: boolean } | null>
  onResetOnboarding: () => void
  embedded?: boolean
}

const CATEGORIES = [
  'career', 'health', 'relationships', 'financial', 'personal_growth',
  'creative', 'education', 'community', 'spiritual', 'other',
]

const frictionColors = ['var(--text-muted)', 'var(--accent-green)', 'var(--accent-amber)', '#f97316', 'var(--accent-red)']

const patternTypeLabels: Record<string, string> = {
  behavioral_drift: 'Drift',
  contradiction: 'Contradiction',
  misallocation: 'Misallocation',
  health: 'Health',
  blindspot: 'Blindspot',
}

export function AdvocacyPanel({
  open, onClose, status, goals, unconfirmedGoals, patterns,
  onCreateGoal, onUpdateGoal, onConfirmGoal, onRejectGoal, onRecordEvidence,
  onDismissPattern, onStartOnboarding, onRespondOnboarding, onResetOnboarding,
  embedded,
}: Props) {
  const [tab, setTab] = useState<'goals' | 'patterns' | 'setup'>('goals')
  const [showGoalForm, setShowGoalForm] = useState(false)
  const [goalText, setGoalText] = useState('')
  const [goalCategory, setGoalCategory] = useState('other')
  const [goalPriority, setGoalPriority] = useState(0.5)
  const [onboardingInput, setOnboardingInput] = useState('')
  const [onboardingPrompt, setOnboardingPrompt] = useState<string | null>(null)

  if (!open) return null

  const handleCreateGoal = () => {
    if (!goalText.trim()) return
    onCreateGoal({ text: goalText, category: goalCategory, priority: goalPriority })
    setGoalText('')
    setGoalCategory('other')
    setGoalPriority(0.5)
    setShowGoalForm(false)
  }

  const handleOnboardingRespond = async () => {
    if (!onboardingInput.trim()) return
    const result = await onRespondOnboarding(onboardingInput)
    setOnboardingInput('')
    if (result?.next_prompt) setOnboardingPrompt(result.next_prompt)
    else setOnboardingPrompt(null)
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '6px 10px', background: 'var(--bg-surface)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)',
    color: 'var(--text)', fontFamily: 'var(--font)', fontSize: '0.8rem',
    outline: 'none', boxSizing: 'border-box',
  }

  const btnStyle: React.CSSProperties = {
    background: 'var(--primary-dim)', border: '1px solid rgba(6, 182, 212, 0.2)',
    color: 'var(--primary)', fontFamily: 'var(--font)', fontSize: '0.7rem',
    fontWeight: 600, padding: '4px 12px', cursor: 'pointer',
    borderRadius: 'var(--radius-xs)',
  }

  const dangerBtnStyle: React.CSSProperties = {
    ...btnStyle, background: 'rgba(239, 68, 68, 0.1)',
    borderColor: 'rgba(239, 68, 68, 0.2)', color: 'var(--accent-red)',
  }

  const successBtnStyle: React.CSSProperties = {
    ...btnStyle, background: 'rgba(34, 197, 94, 0.1)',
    borderColor: 'rgba(34, 197, 94, 0.2)', color: 'var(--accent-green)',
  }

  return (
    <div style={{
      position: embedded ? 'relative' : 'fixed',
      top: embedded ? 'auto' : 0, right: embedded ? 'auto' : 0,
      width: embedded ? '100%' : 420, height: embedded ? '100%' : '100vh',
      background: 'var(--bg-secondary)',
      borderLeft: embedded ? 'none' : '1px solid var(--border)',
      zIndex: embedded ? 'auto' : 100, display: 'flex', flexDirection: 'column',
      boxShadow: embedded ? 'none' : '-4px 0 16px rgba(0,0,0,0.3)',
      flex: embedded ? 1 : undefined, overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text)' }}>
          Advocacy
        </span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)',
          cursor: 'pointer', fontSize: '1rem',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        {(['goals', 'patterns', 'setup'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            flex: 1, padding: '8px', background: 'none', border: 'none',
            borderBottom: tab === t ? '2px solid var(--primary)' : '2px solid transparent',
            color: tab === t ? 'var(--primary)' : 'var(--text-muted)',
            fontFamily: 'var(--font)', fontSize: '0.75rem', fontWeight: 600,
            cursor: 'pointer', textTransform: 'capitalize',
          }}>
            {t === 'goals' ? `Goals (${goals.length})` : t === 'patterns' ? `Patterns (${patterns.length})` : 'Setup'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>

        {/* Goals Tab */}
        {tab === 'goals' && (
          <>
            <button onClick={() => setShowGoalForm(!showGoalForm)} style={{ ...btnStyle, marginBottom: 12 }}>
              {showGoalForm ? 'Cancel' : '+ New Goal'}
            </button>

            {showGoalForm && (
              <div style={{
                padding: 12, marginBottom: 12, background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              }}>
                <input placeholder="What do you want to achieve?"
                  value={goalText} onChange={e => setGoalText(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }}
                  onKeyDown={e => e.key === 'Enter' && handleCreateGoal()}
                />
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <select value={goalCategory} onChange={e => setGoalCategory(e.target.value)}
                    style={{ ...inputStyle, width: 'auto' }}>
                    {CATEGORIES.map(c => (
                      <option key={c} value={c}>{c.replace('_', ' ')}</option>
                    ))}
                  </select>
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Priority:</span>
                    <input type="range" min="0" max="1" step="0.1"
                      value={goalPriority} onChange={e => setGoalPriority(parseFloat(e.target.value))}
                      style={{ flex: 1 }}
                    />
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', minWidth: 24 }}>
                      {goalPriority.toFixed(1)}
                    </span>
                  </div>
                </div>
                <button onClick={handleCreateGoal} style={btnStyle}>Create Goal</button>
              </div>
            )}

            {/* Unconfirmed Goals */}
            {unconfirmedGoals.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{
                  fontSize: '0.7rem', fontWeight: 700, color: 'var(--accent-amber)',
                  textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em',
                }}>
                  Inferred — Needs Confirmation ({unconfirmedGoals.length})
                </div>
                {unconfirmedGoals.map(goal => (
                  <div key={goal.id} style={{
                    padding: '10px 12px', marginBottom: 8,
                    background: 'var(--bg-surface)', border: '1px solid rgba(245, 158, 11, 0.3)',
                    borderRadius: 'var(--radius-sm)',
                  }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
                      {goal.text}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                      {goal.category.replace('_', ' ')} — priority {goal.priority.toFixed(1)}
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => onConfirmGoal(goal.id)} style={successBtnStyle}>Confirm</button>
                      <button onClick={() => onRejectGoal(goal.id)} style={dangerBtnStyle}>Reject</button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Active Goals */}
            {goals.length === 0 && unconfirmedGoals.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
                No goals yet. Add one to get started.
              </div>
            )}

            {goals.map(goal => (
              <div key={goal.id} style={{
                padding: '10px 12px', marginBottom: 8,
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                    {goal.text}
                  </span>
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
                    borderRadius: 4, background: 'rgba(6, 182, 212, 0.1)',
                    color: 'var(--primary)', textTransform: 'uppercase',
                  }}>{goal.category.replace('_', ' ')}</span>
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                  Priority: {goal.priority.toFixed(1)} — Evidence: {goal.evidence.length}
                  {goal.tensions.length > 0 && ` — Tensions: ${goal.tensions.length}`}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => onUpdateGoal(goal.id, { status: 'completed' })} style={successBtnStyle}>
                    Complete
                  </button>
                  <button onClick={() => onUpdateGoal(goal.id, { status: 'abandoned' })} style={dangerBtnStyle}>
                    Abandon
                  </button>
                </div>
              </div>
            ))}
          </>
        )}

        {/* Patterns Tab */}
        {tab === 'patterns' && (
          <>
            {patterns.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
                No active patterns detected yet
              </div>
            )}

            {patterns.map(pattern => (
              <div key={pattern.id} style={{
                padding: '10px 12px', marginBottom: 8,
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                    background: frictionColors[pattern.friction_level] || frictionColors[0],
                  }} />
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                    {pattern.description}
                  </span>
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
                    borderRadius: 4, background: 'rgba(6, 182, 212, 0.1)',
                    color: 'var(--primary)', textTransform: 'uppercase',
                  }}>{patternTypeLabels[pattern.type] || pattern.type}</span>
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                  Occurrences: {pattern.occurrences} — Friction: {pattern.friction_level}/4
                  {pattern.related_goals.length > 0 && ` — Goals: ${pattern.related_goals.length}`}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => onDismissPattern(pattern.id)} style={btnStyle}>Dismiss</button>
                </div>
              </div>
            ))}
          </>
        )}

        {/* Setup Tab */}
        {tab === 'setup' && (
          <>
            {/* Status summary */}
            {status && (
              <div style={{
                padding: 12, marginBottom: 12, background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
                  System Status
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.8 }}>
                  Profile: {status.profile}<br />
                  Active goals: {status.active_goals}<br />
                  Unconfirmed goals: {status.unconfirmed_goals}<br />
                  Active patterns: {status.active_patterns}
                  {status.friction && (<><br />Flags today: {status.friction.flags_today}/{status.friction.max_flags_per_day}</>)}
                  {status.developmental && (<><br />Developmental: {status.developmental.mode}</>)}
                </div>
              </div>
            )}

            {/* Onboarding */}
            <div style={{
              padding: 12, background: 'var(--bg-surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
            }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
                Onboarding
              </div>

              {status?.onboarding?.complete ? (
                <>
                  <div style={{ fontSize: '0.7rem', color: 'var(--accent-green)', marginBottom: 8 }}>
                    Onboarding complete
                  </div>
                  <button onClick={onResetOnboarding} style={dangerBtnStyle}>Reset Onboarding</button>
                </>
              ) : status?.onboarding?.started ? (
                <>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                    Stage: {status.onboarding.stage}
                  </div>
                  {onboardingPrompt && (
                    <div style={{
                      fontSize: '0.75rem', color: 'var(--text)', marginBottom: 8,
                      padding: 8, background: 'var(--bg-secondary)', borderRadius: 'var(--radius-xs)',
                    }}>
                      {onboardingPrompt}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <input placeholder="Your response..."
                      value={onboardingInput} onChange={e => setOnboardingInput(e.target.value)}
                      style={{ ...inputStyle, flex: 1 }}
                      onKeyDown={e => e.key === 'Enter' && handleOnboardingRespond()}
                    />
                    <button onClick={handleOnboardingRespond} style={btnStyle}>Send</button>
                  </div>
                </>
              ) : (
                <button onClick={onStartOnboarding} style={btnStyle}>Start Onboarding</button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
