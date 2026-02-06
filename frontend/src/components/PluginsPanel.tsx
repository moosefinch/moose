import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'

interface PluginInfo {
  id: string
  name: string
  version: string
  description?: string
  author?: string
  provides?: string[]
  dependencies?: string[]
  _installed: boolean
  _loaded: boolean
  _no_manifest?: boolean
}

interface Props {
  open: boolean
  onClose: () => void
  embedded?: boolean
}

export function PluginsPanel({ open, onClose, embedded }: Props) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [installUrl, setInstallUrl] = useState('')
  const [installing, setInstalling] = useState(false)
  const [error, setError] = useState('')

  const loadPlugins = useCallback(async () => {
    try {
      const r = await apiFetch('/api/plugins')
      if (r.ok) setPlugins(await r.json())
    } catch (e) {
      console.error('[PluginsPanel] load error:', e)
    }
  }, [])

  useEffect(() => {
    if (open) loadPlugins()
  }, [open, loadPlugins])

  const handleInstall = async () => {
    if (!installUrl.trim()) return
    setInstalling(true)
    setError('')
    try {
      const r = await apiFetch('/api/plugins/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: installUrl }),
      })
      if (r.ok) {
        setInstallUrl('')
        await loadPlugins()
      } else {
        const data = await r.json()
        setError(data.detail || 'Install failed')
      }
    } catch (e) {
      setError('Install failed')
    } finally {
      setInstalling(false)
    }
  }

  const handleRemove = async (pluginId: string) => {
    try {
      const r = await apiFetch(`/api/plugins/${pluginId}`, { method: 'DELETE' })
      if (r.ok) await loadPlugins()
      else {
        const data = await r.json()
        setError(data.detail || 'Remove failed')
      }
    } catch (e) {
      setError('Remove failed')
    }
  }

  if (!open) return null

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
          Plugins
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

      {/* Install form */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            placeholder="Git repository URL..."
            value={installUrl}
            onChange={e => setInstallUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleInstall()}
            style={{
              flex: 1, padding: '6px 10px', background: 'var(--bg-surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)',
              color: 'var(--text)', fontFamily: 'var(--font)', fontSize: '0.8rem',
              outline: 'none',
            }}
          />
          <button
            onClick={handleInstall}
            disabled={installing}
            style={{
              background: 'var(--primary-dim)', border: '1px solid rgba(6, 182, 212, 0.2)',
              color: 'var(--primary)', fontFamily: 'var(--font)', fontSize: '0.7rem',
              fontWeight: 600, padding: '4px 12px', cursor: installing ? 'default' : 'pointer',
              borderRadius: 'var(--radius-xs)',
            }}
          >{installing ? '...' : 'Install'}</button>
        </div>
        {error && (
          <div style={{ color: 'var(--accent-red)', fontSize: '0.7rem', marginTop: 4 }}>{error}</div>
        )}
      </div>

      {/* Plugin list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {plugins.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textAlign: 'center', padding: 20 }}>
            No plugins found
          </div>
        )}

        <div style={{ display: 'grid', gap: 10 }}>
          {plugins.map(p => (
            <div key={p.id} style={{
              padding: '12px', background: 'var(--bg-surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text)', flex: 1 }}>
                  {p.name}
                </span>
                <span style={{
                  fontSize: '0.6rem', fontWeight: 700, padding: '1px 6px',
                  borderRadius: 4, textTransform: 'uppercase',
                  background: p._loaded ? 'rgba(34, 197, 94, 0.1)' : 'rgba(107, 114, 128, 0.1)',
                  color: p._loaded ? 'var(--accent-green)' : 'var(--text-muted)',
                }}>{p._loaded ? 'Active' : 'Installed'}</span>
              </div>
              {p.description && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: 6 }}>
                  {p.description}
                </div>
              )}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: '0.65rem', color: 'var(--text-muted)',
              }}>
                <span>v{p.version}</span>
                {p.author && <span>by {p.author}</span>}
                {p.provides && p.provides.length > 0 && (
                  <span>{p.provides.join(', ')}</span>
                )}
              </div>
              {!['crm', 'telegram', 'slack'].includes(p.id) && (
                <button
                  onClick={() => handleRemove(p.id)}
                  style={{
                    marginTop: 8, background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    color: 'var(--accent-red)', fontFamily: 'var(--font)',
                    fontSize: '0.65rem', fontWeight: 600, padding: '3px 10px',
                    cursor: 'pointer', borderRadius: 'var(--radius-xs)',
                  }}
                >Remove</button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
