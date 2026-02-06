import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import type { AdvocacyGoal, AdvocacyPattern, AdvocacyStatus } from '../types'

export function useAdvocacy() {
  const [status, setStatus] = useState<AdvocacyStatus | null>(null)
  const [goals, setGoals] = useState<AdvocacyGoal[]>([])
  const [unconfirmedGoals, setUnconfirmedGoals] = useState<AdvocacyGoal[]>([])
  const [patterns, setPatterns] = useState<AdvocacyPattern[]>([])

  const loadStatus = useCallback(async () => {
    try {
      const r = await apiFetch('/api/advocacy/status')
      if (r.ok) setStatus(await r.json())
    } catch { /* ignore */ }
  }, [])

  const loadGoals = useCallback(async () => {
    try {
      const r = await apiFetch('/api/advocacy/goals')
      if (r.ok) {
        const data = await r.json()
        setGoals(data.active || [])
        setUnconfirmedGoals(data.unconfirmed || [])
      }
    } catch { /* ignore */ }
  }, [])

  const loadPatterns = useCallback(async () => {
    try {
      const r = await apiFetch('/api/advocacy/patterns')
      if (r.ok) setPatterns(await r.json())
    } catch { /* ignore */ }
  }, [])

  const refresh = useCallback(() => {
    loadStatus()
    loadGoals()
    loadPatterns()
  }, [loadStatus, loadGoals, loadPatterns])

  // Poll every 30s
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30000)
    return () => clearInterval(id)
  }, [refresh])

  const createGoal = useCallback(async (data: { text: string; category?: string; priority?: number; parent_id?: string }) => {
    try {
      const r = await apiFetch('/api/advocacy/goals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadGoals()
        return await r.json()
      }
    } catch (e) {
      console.error('[useAdvocacy] create goal error:', e)
    }
    return null
  }, [loadGoals])

  const updateGoal = useCallback(async (goalId: string, data: { status?: string; priority?: number }) => {
    try {
      const r = await apiFetch(`/api/advocacy/goals/${goalId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadGoals()
        return await r.json()
      }
    } catch (e) {
      console.error('[useAdvocacy] update goal error:', e)
    }
    return null
  }, [loadGoals])

  const confirmGoal = useCallback(async (goalId: string) => {
    try {
      const r = await apiFetch(`/api/advocacy/goals/${goalId}/confirm`, { method: 'POST' })
      if (r.ok) await loadGoals()
      return r.ok
    } catch (e) {
      console.error('[useAdvocacy] confirm goal error:', e)
      return false
    }
  }, [loadGoals])

  const rejectGoal = useCallback(async (goalId: string) => {
    try {
      const r = await apiFetch(`/api/advocacy/goals/${goalId}/reject`, { method: 'POST' })
      if (r.ok) await loadGoals()
      return r.ok
    } catch (e) {
      console.error('[useAdvocacy] reject goal error:', e)
      return false
    }
  }, [loadGoals])

  const recordEvidence = useCallback(async (goalId: string, data: { type?: string; description: string }) => {
    try {
      const r = await apiFetch(`/api/advocacy/goals/${goalId}/evidence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) await loadGoals()
      return r.ok
    } catch (e) {
      console.error('[useAdvocacy] record evidence error:', e)
      return false
    }
  }, [loadGoals])

  const dismissPattern = useCallback(async (patternId: string) => {
    try {
      const r = await apiFetch(`/api/advocacy/patterns/${patternId}/dismiss`, { method: 'POST' })
      if (r.ok) await loadPatterns()
      return r.ok
    } catch (e) {
      console.error('[useAdvocacy] dismiss pattern error:', e)
      return false
    }
  }, [loadPatterns])

  const startOnboarding = useCallback(async () => {
    try {
      const r = await apiFetch('/api/advocacy/onboarding/start', { method: 'POST' })
      if (r.ok) {
        await loadStatus()
        return await r.json()
      }
    } catch (e) {
      console.error('[useAdvocacy] start onboarding error:', e)
    }
    return null
  }, [loadStatus])

  const respondOnboarding = useCallback(async (text: string) => {
    try {
      const r = await apiFetch('/api/advocacy/onboarding/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (r.ok) {
        await loadStatus()
        return await r.json()
      }
    } catch (e) {
      console.error('[useAdvocacy] respond onboarding error:', e)
    }
    return null
  }, [loadStatus])

  const resetOnboarding = useCallback(async () => {
    try {
      const r = await apiFetch('/api/advocacy/onboarding/reset', { method: 'POST' })
      if (r.ok) await loadStatus()
      return r.ok
    } catch (e) {
      console.error('[useAdvocacy] reset onboarding error:', e)
      return false
    }
  }, [loadStatus])

  return {
    status, goals, unconfirmedGoals, patterns,
    createGoal, updateGoal, confirmGoal, rejectGoal, recordEvidence,
    dismissPattern,
    startOnboarding, respondOnboarding, resetOnboarding,
    refresh,
  }
}
