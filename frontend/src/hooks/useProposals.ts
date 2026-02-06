import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import type { ImprovementProposal } from '../types'

export function useProposals() {
  const [proposals, setProposals] = useState<ImprovementProposal[]>([])
  const [loading, setLoading] = useState(false)

  const loadProposals = useCallback(async () => {
    try {
      const r = await apiFetch('/api/proposals')
      if (r.ok) setProposals(await r.json())
    } catch (e) {
      console.error('[useProposals] load error:', e)
    }
  }, [])

  const approveProposal = useCallback(async (id: string, notes = '') => {
    try {
      const r = await apiFetch(`/api/proposals/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true, notes }),
      })
      if (r.ok) {
        await loadProposals()
        return await r.json()
      }
    } catch (e) {
      console.error('[useProposals] approve error:', e)
    }
    return null
  }, [loadProposals])

  const rejectProposal = useCallback(async (id: string, notes = '') => {
    try {
      const r = await apiFetch(`/api/proposals/${id}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: false, notes }),
      })
      if (r.ok) {
        await loadProposals()
        return await r.json()
      }
    } catch (e) {
      console.error('[useProposals] reject error:', e)
    }
    return null
  }, [loadProposals])

  const pendingProposals = proposals.filter(p => p.status === 'pending')

  // Poll every 15s
  useEffect(() => {
    loadProposals()
    const id = setInterval(loadProposals, 15000)
    return () => clearInterval(id)
  }, [loadProposals])

  return { proposals, pendingProposals, loading, approveProposal, rejectProposal, refresh: loadProposals }
}
