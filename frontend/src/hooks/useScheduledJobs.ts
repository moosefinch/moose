import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import type { ScheduledJob } from '../types'

export function useScheduledJobs() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([])
  const [loading, setLoading] = useState(false)

  const loadJobs = useCallback(async () => {
    try {
      const r = await apiFetch('/api/scheduled-jobs')
      if (r.ok) setJobs(await r.json())
    } catch (e) {
      console.error('[useScheduledJobs] load error:', e)
    }
  }, [])

  const createJob = useCallback(async (data: {
    description: string
    schedule_type: string
    schedule_value: string
    agent_id?: string
    task_payload?: string
  }) => {
    try {
      const r = await apiFetch('/api/scheduled-jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadJobs()
        return await r.json()
      }
    } catch (e) {
      console.error('[useScheduledJobs] create error:', e)
    }
    return null
  }, [loadJobs])

  const updateJob = useCallback(async (jobId: string, data: Record<string, unknown>) => {
    try {
      const r = await apiFetch(`/api/scheduled-jobs/${jobId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadJobs()
        return await r.json()
      }
    } catch (e) {
      console.error('[useScheduledJobs] update error:', e)
    }
    return null
  }, [loadJobs])

  const deleteJob = useCallback(async (jobId: string) => {
    try {
      const r = await apiFetch(`/api/scheduled-jobs/${jobId}`, { method: 'DELETE' })
      if (r.ok) await loadJobs()
      return r.ok
    } catch (e) {
      console.error('[useScheduledJobs] delete error:', e)
      return false
    }
  }, [loadJobs])

  const parseNatural = useCallback(async (text: string) => {
    try {
      const r = await apiFetch('/api/scheduled-jobs/parse-natural', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (r.ok) return await r.json()
    } catch (e) {
      console.error('[useScheduledJobs] parse error:', e)
    }
    return null
  }, [])

  // Poll every 15s
  useEffect(() => {
    loadJobs()
    const id = setInterval(loadJobs, 15000)
    return () => clearInterval(id)
  }, [loadJobs])

  return { jobs, loading, createJob, updateJob, deleteJob, parseNatural, refresh: loadJobs }
}
