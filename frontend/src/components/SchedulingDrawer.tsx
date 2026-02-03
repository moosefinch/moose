import { useState } from 'react'
import type { ScheduledJob, WebhookEndpoint } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  jobs: ScheduledJob[]
  onCreateJob: (data: { description: string; schedule_type: string; schedule_value: string }) => void
  onUpdateJob: (jobId: string, data: Record<string, unknown>) => void
  onDeleteJob: (jobId: string) => void
  onParseNatural: (text: string) => Promise<{ schedule_type: string; schedule_value: string } | null>
  // Webhook props (Phase 6)
  webhooks?: WebhookEndpoint[]
  onCreateWebhook?: (data: Record<string, unknown>) => void
  onUpdateWebhook?: (id: string, data: Record<string, unknown>) => void
  onDeleteWebhook?: (id: string) => void
  embedded?: boolean
}

function formatRelative(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const now = new Date()
  const diff = d.getTime() - now.getTime()
  const absDiff = Math.abs(diff)
  if (absDiff < 60000) return diff > 0 ? 'in <1m' : '<1m ago'
  if (absDiff < 3600000) {
    const mins = Math.floor(absDiff / 60000)
    return diff > 0 ? `in ${mins}m` : `${mins}m ago`
  }
  if (absDiff < 86400000) {
    const hrs = Math.floor(absDiff / 3600000)
    return diff > 0 ? `in ${hrs}h` : `${hrs}h ago`
  }
  return d.toLocaleString()
}

const typeBadgeColor: Record<string, string> = {
  interval: 'var(--primary)',
  cron: 'var(--accent-amber)',
  once: 'var(--accent-green)',
}

export function SchedulingDrawer({
  open, onClose, jobs, onCreateJob, onUpdateJob, onDeleteJob, onParseNatural,
  webhooks, onCreateWebhook, onUpdateWebhook, onDeleteWebhook, embedded,
}: Props) {
  const [tab, setTab] = useState<'jobs' | 'webhooks'>('jobs')
  const [showForm, setShowForm] = useState(false)
  const [desc, setDesc] = useState('')
  const [schedType, setSchedType] = useState('interval')
  const [schedValue, setSchedValue] = useState('')
  const [naturalText, setNaturalText] = useState('')

  // Webhook form state
  const [showWebhookForm, setShowWebhookForm] = useState(false)
  const [whName, setWhName] = useState('')
  const [whSlug, setWhSlug] = useState('')
  const [whSourceType, setWhSourceType] = useState('generic')
  const [whActionType, setWhActionType] = useState('start_task')
  const [whActionPayload, setWhActionPayload] = useState('')

  if (!open) return null

  const handleCreate = () => {
    if (!desc.trim() || !schedValue.trim()) return
    onCreateJob({ description: desc, schedule_type: schedType, schedule_value: schedValue })
    setDesc('')
    setSchedValue('')
    setShowForm(false)
  }

  const handleParseNatural = async () => {
    if (!naturalText.trim()) return
    const parsed = await onParseNatural(naturalText)
    if (parsed) {
      setSchedType(parsed.schedule_type)
      setSchedValue(parsed.schedule_value)
    }
  }

  const handleCreateWebhook = () => {
    if (!whName.trim() || !whSlug.trim() || !onCreateWebhook) return
    onCreateWebhook({
      name: whName, slug: whSlug, source_type: whSourceType,
      action_type: whActionType, action_payload: whActionPayload,
    })
    setWhName('')
    setWhSlug('')
    setWhActionPayload('')
    setShowWebhookForm(false)
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '6px 10px', background: 'var(--bg-surface)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)',
    color: 'var(--text)', fontFamily: 'var(--font)', fontSize: '0.8rem',
    outline: 'none',
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
          Scheduling & Triggers
        </span>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: 'var(--text-muted)',
          cursor: 'pointer', fontSize: '1rem',
        }}>{'\u2715'}</button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={() => setTab('jobs')}
          style={{
            flex: 1, padding: '8px', background: 'none', border: 'none',
            borderBottom: tab === 'jobs' ? '2px solid var(--primary)' : '2px solid transparent',
            color: tab === 'jobs' ? 'var(--primary)' : 'var(--text-muted)',
            fontFamily: 'var(--font)', fontSize: '0.75rem', fontWeight: 600,
            cursor: 'pointer',
          }}
        >Scheduled Jobs ({jobs.length})</button>
        <button
          onClick={() => setTab('webhooks')}
          style={{
            flex: 1, padding: '8px', background: 'none', border: 'none',
            borderBottom: tab === 'webhooks' ? '2px solid var(--primary)' : '2px solid transparent',
            color: tab === 'webhooks' ? 'var(--primary)' : 'var(--text-muted)',
            fontFamily: 'var(--font)', fontSize: '0.75rem', fontWeight: 600,
            cursor: 'pointer',
          }}
        >Webhooks ({webhooks?.length || 0})</button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {tab === 'jobs' && (
          <>
            <button onClick={() => setShowForm(!showForm)} style={{ ...btnStyle, marginBottom: 12 }}>
              {showForm ? 'Cancel' : '+ New Job'}
            </button>

            {showForm && (
              <div style={{
                padding: 12, marginBottom: 12, background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              }}>
                <input
                  placeholder="Description (e.g., Check server health)"
                  value={desc} onChange={e => setDesc(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }}
                />
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <input
                    placeholder="Natural language (e.g., every 30 minutes)"
                    value={naturalText} onChange={e => setNaturalText(e.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                    onKeyDown={e => e.key === 'Enter' && handleParseNatural()}
                  />
                  <button onClick={handleParseNatural} style={btnStyle}>Parse</button>
                </div>
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <select value={schedType} onChange={e => setSchedType(e.target.value)}
                    style={{ ...inputStyle, width: 'auto' }}>
                    <option value="interval">Interval</option>
                    <option value="cron">Cron</option>
                    <option value="once">One-shot</option>
                  </select>
                  <input
                    placeholder={schedType === 'interval' ? 'Seconds (e.g., 3600)' :
                      schedType === 'cron' ? 'Cron expr (e.g., 0 */2 * * *)' : 'ISO timestamp'}
                    value={schedValue} onChange={e => setSchedValue(e.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                  />
                </div>
                <button onClick={handleCreate} style={btnStyle}>Create Job</button>
              </div>
            )}

            {jobs.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
                No scheduled jobs yet
              </div>
            )}

            {jobs.map(job => (
              <div key={job.id} style={{
                padding: '10px 12px', marginBottom: 8,
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', opacity: job.enabled ? 1 : 0.5,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                    {job.description}
                  </span>
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
                    borderRadius: 4, background: `${typeBadgeColor[job.schedule_type] || 'var(--text-muted)'}22`,
                    color: typeBadgeColor[job.schedule_type] || 'var(--text-muted)',
                    textTransform: 'uppercase',
                  }}>{job.schedule_type}</span>
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 6 }}>
                  Next: {formatRelative(job.next_run)} | Last: {formatRelative(job.last_run)} | Runs: {job.run_count}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => onUpdateJob(job.id, { enabled: !job.enabled })}
                    style={btnStyle}
                  >{job.enabled ? 'Disable' : 'Enable'}</button>
                  <button onClick={() => onDeleteJob(job.id)} style={dangerBtnStyle}>Delete</button>
                </div>
              </div>
            ))}
          </>
        )}

        {tab === 'webhooks' && (
          <>
            {onCreateWebhook && (
              <button onClick={() => setShowWebhookForm(!showWebhookForm)} style={{ ...btnStyle, marginBottom: 12 }}>
                {showWebhookForm ? 'Cancel' : '+ New Webhook'}
              </button>
            )}

            {showWebhookForm && onCreateWebhook && (
              <div style={{
                padding: 12, marginBottom: 12, background: 'var(--bg-surface)',
                border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              }}>
                <input placeholder="Name" value={whName} onChange={e => setWhName(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }} />
                <input placeholder="Slug (URL path)" value={whSlug} onChange={e => setWhSlug(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }} />
                <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                  <select value={whSourceType} onChange={e => setWhSourceType(e.target.value)}
                    style={{ ...inputStyle, width: 'auto' }}>
                    <option value="generic">Generic</option>
                    <option value="github">GitHub</option>
                  </select>
                  <select value={whActionType} onChange={e => setWhActionType(e.target.value)}
                    style={{ ...inputStyle, width: 'auto' }}>
                    <option value="start_task">Start Task</option>
                    <option value="chat">Chat</option>
                    <option value="notify">Notify</option>
                  </select>
                </div>
                <input placeholder="Action payload (optional)" value={whActionPayload}
                  onChange={e => setWhActionPayload(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }} />
                <button onClick={handleCreateWebhook} style={btnStyle}>Create Webhook</button>
              </div>
            )}

            {(!webhooks || webhooks.length === 0) && (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
                No webhooks configured
              </div>
            )}

            {webhooks?.map(wh => (
              <div key={wh.id} style={{
                padding: '10px 12px', marginBottom: 8,
                background: 'var(--bg-surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', opacity: wh.enabled ? 1 : 0.5,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                    {wh.name}
                  </span>
                  <span style={{
                    fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
                    borderRadius: 4, background: 'rgba(6, 182, 212, 0.1)',
                    color: 'var(--primary)', textTransform: 'uppercase',
                  }}>{wh.source_type}</span>
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 6, fontFamily: 'monospace' }}>
                  /api/webhooks/receive/{wh.slug}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {onUpdateWebhook && (
                    <button onClick={() => onUpdateWebhook(wh.id, { enabled: !wh.enabled })}
                      style={btnStyle}>{wh.enabled ? 'Disable' : 'Enable'}</button>
                  )}
                  {onDeleteWebhook && (
                    <button onClick={() => onDeleteWebhook(wh.id)} style={dangerBtnStyle}>Delete</button>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
