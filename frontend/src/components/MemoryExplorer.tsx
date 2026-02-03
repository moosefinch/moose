import { useState, useRef, useCallback, useEffect } from 'react'
import type { MemorySearchResult } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  memoryCount: number
  onSearch: (query: string, topK?: number) => Promise<MemorySearchResult[]>
  embedded?: boolean
}

export function MemoryExplorer({ open, onClose, memoryCount, onSearch, embedded }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemorySearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100)
    } else {
      setQuery('')
      setResults([])
    }
  }, [open])

  useEffect(() => {
    if (!open || embedded) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose, embedded])

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return }
    setSearching(true)
    try {
      const r = await onSearch(q.trim())
      setResults(r)
    } finally {
      setSearching(false)
    }
  }, [onSearch])

  const handleInput = useCallback((value: string) => {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(value), 300)
  }, [doSearch])

  if (!open) return null

  const headerAndContent = (
    <>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
      }}>
        <div>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '1px', color: 'var(--text)' }}>
            MEMORY
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 2 }}>
            {memoryCount.toLocaleString()} memories stored
          </div>
        </div>
        {!embedded && <button onClick={onClose} style={{
          background: 'none', border: '1px solid var(--border)',
          color: 'var(--text-muted)', fontSize: '0.7rem', fontWeight: 500,
          padding: '4px 8px', cursor: 'pointer', borderRadius: 'var(--radius-xs)',
          fontFamily: 'var(--font)',
        }}>ESC</button>}
      </div>

        {/* Search input */}
        <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--border)' }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => handleInput(e.target.value)}
            placeholder="Search memory..."
            maxLength={500}
            style={{
              width: '100%', background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: '8px 12px', color: 'var(--text)',
              fontSize: '0.8rem', fontFamily: 'var(--font)', outline: 'none',
            }}
            onFocus={e => { e.target.style.borderColor = 'rgba(6, 182, 212, 0.4)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)' }}
          />
        </div>

        {/* Results */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {searching && (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              Searching...
            </div>
          )}

          {!searching && query && results.length === 0 && (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              No memories found
            </div>
          )}

          {!searching && !query && (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              Type to search memory...
            </div>
          )}

          {results.map((result, i) => (
            <div key={i} style={{
              padding: '10px 16px', borderBottom: '1px solid var(--border)',
            }}>
              {/* Relevance bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <div style={{
                  flex: 1, height: '2px', background: 'var(--bg-tertiary)',
                  borderRadius: '1px', overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', borderRadius: '1px', transition: 'width 0.3s',
                    background: result.score > 0.7 ? 'var(--accent-green)' : result.score > 0.4 ? 'var(--primary)' : 'var(--text-muted)',
                    width: `${Math.min(result.score * 100, 100)}%`,
                  }} />
                </div>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                  {(result.score * 100).toFixed(0)}%
                </span>
              </div>

              {/* Text preview */}
              <div style={{
                fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.5,
                maxHeight: '54px', overflow: 'hidden',
                WebkitMaskImage: 'linear-gradient(180deg, #000 60%, transparent)',
                maskImage: 'linear-gradient(180deg, #000 60%, transparent)',
              }}>
                {result.text}
              </div>

              {/* Metadata */}
              <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
                {result.timestamp && (
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                    {new Date(result.timestamp).toLocaleDateString()}
                  </span>
                )}
                {result.tags && (
                  <span style={{ fontSize: '0.65rem', color: 'var(--primary)', background: 'var(--primary-dim)', padding: '1px 5px', borderRadius: '6px' }}>
                    {result.tags}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
    </>
  )

  if (embedded) {
    return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>{headerAndContent}</div>
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer-right">{headerAndContent}</div>
    </>
  )
}
