import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import type { PendingEmail, ContentDraft, MarketingStats } from '../types'

export function useMarketing() {
  const [pendingEmails, setPendingEmails] = useState<PendingEmail[]>([])
  const [pendingContent, setPendingContent] = useState<ContentDraft[]>([])
  const [stats, setStats] = useState<MarketingStats | null>(null)

  const fetchEmails = useCallback(async () => {
    try {
      const res = await apiFetch('/api/marketing/emails?status=pending')
      if (res.ok) setPendingEmails(await res.json())
    } catch { /* ignore */ }
  }, [])

  const fetchContent = useCallback(async () => {
    try {
      const res = await apiFetch('/api/content?status=drafted')
      if (res.ok) setPendingContent(await res.json())
    } catch { /* ignore */ }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiFetch('/api/marketing/stats')
      if (res.ok) setStats(await res.json())
    } catch { /* ignore */ }
  }, [])

  const refresh = useCallback(() => {
    fetchEmails()
    fetchContent()
    fetchStats()
  }, [fetchEmails, fetchContent, fetchStats])

  // Poll every 15s
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 15000)
    return () => clearInterval(id)
  }, [refresh])

  const approveEmail = useCallback(async (emailId: string) => {
    try {
      await apiFetch(`/api/marketing/emails/${emailId}/approve`, { method: 'POST' })
      refresh()
    } catch { /* ignore */ }
  }, [refresh])

  const rejectEmail = useCallback(async (emailId: string) => {
    try {
      await apiFetch(`/api/marketing/emails/${emailId}/reject`, { method: 'POST' })
      refresh()
    } catch { /* ignore */ }
  }, [refresh])

  const editEmail = useCallback(async (emailId: string, subject: string, body: string) => {
    try {
      await apiFetch(`/api/marketing/emails/${emailId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, body }),
      })
      refresh()
    } catch { /* ignore */ }
  }, [refresh])

  const approveContent = useCallback(async (draftId: string) => {
    try {
      await apiFetch(`/api/content/${draftId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'reviewed' }),
      })
      refresh()
    } catch { /* ignore */ }
  }, [refresh])

  const rejectContent = useCallback(async (draftId: string) => {
    try {
      await apiFetch(`/api/content/${draftId}`, { method: 'DELETE' })
      refresh()
    } catch { /* ignore */ }
  }, [refresh])

  const totalPending = pendingEmails.length + pendingContent.length

  return {
    pendingEmails, pendingContent, stats, totalPending,
    approveEmail, rejectEmail, editEmail,
    approveContent, rejectContent, refresh,
  }
}
