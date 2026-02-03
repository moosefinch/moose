import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import type { WebhookEndpoint } from '../types'

export function useWebhooks() {
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[]>([])

  const loadWebhooks = useCallback(async () => {
    try {
      const r = await apiFetch('/api/webhooks')
      if (r.ok) setWebhooks(await r.json())
    } catch (e) {
      console.error('[useWebhooks] load error:', e)
    }
  }, [])

  const createWebhook = useCallback(async (data: Record<string, unknown>) => {
    try {
      const r = await apiFetch('/api/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadWebhooks()
        return await r.json()
      }
    } catch (e) {
      console.error('[useWebhooks] create error:', e)
    }
    return null
  }, [loadWebhooks])

  const updateWebhook = useCallback(async (id: string, data: Record<string, unknown>) => {
    try {
      const r = await apiFetch(`/api/webhooks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (r.ok) {
        await loadWebhooks()
        return await r.json()
      }
    } catch (e) {
      console.error('[useWebhooks] update error:', e)
    }
    return null
  }, [loadWebhooks])

  const deleteWebhook = useCallback(async (id: string) => {
    try {
      const r = await apiFetch(`/api/webhooks/${id}`, { method: 'DELETE' })
      if (r.ok) await loadWebhooks()
      return r.ok
    } catch (e) {
      console.error('[useWebhooks] delete error:', e)
      return false
    }
  }, [loadWebhooks])

  useEffect(() => {
    loadWebhooks()
    const id = setInterval(loadWebhooks, 30000)
    return () => clearInterval(id)
  }, [loadWebhooks])

  return { webhooks, createWebhook, updateWebhook, deleteWebhook, refresh: loadWebhooks }
}
