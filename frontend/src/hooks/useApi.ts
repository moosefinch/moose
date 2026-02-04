import { useState, useEffect, useCallback } from 'react'
import { apiUrl, apiFetch, getApiKey } from '../api'
import type { Conversation, AgentTask, Briefing, ModelStatus, ChatMessage, MemorySearchResult } from '../types'

export function useApi() {
  const [apiUp, setApiUp] = useState(false)
  const [modelStatus, setModelStatus] = useState<Record<string, ModelStatus>>({})
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [briefings, setBriefings] = useState<Briefing[]>([])
  const [memoryCount, setMemoryCount] = useState(0)

  // Health check
  useEffect(() => {
    const check = async () => {
      try {
        const r = await apiFetch('/health')
        setApiUp(r.ok)
        const mr = await apiFetch('/api/models')
        if (!mr.ok) return
        const md = await mr.json()
        setModelStatus(md.models || {})
      } catch { setApiUp(false) }
    }
    check()
    const id = setInterval(check, 5000)
    return () => clearInterval(id)
  }, [])

  // Load conversations
  const loadConversations = useCallback(async () => {
    try {
      const r = await apiFetch('/conversations')
      if (!r.ok) return
      const data = await r.json()
      if (Array.isArray(data)) setConversations(data)
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [])

  const createConversation = useCallback(async () => {
    try {
      const r = await apiFetch('/conversations', { method: 'POST' })
      if (!r.ok) return null
      const data = await r.json()
      setConversations(prev => [data, ...prev])
      return data as Conversation
    } catch (e) { console.error('[useApi] Create conversation failed:', e); return null }
  }, [])

  const loadConversationMessages = useCallback(async (convId: string): Promise<ChatMessage[]> => {
    try {
      const r = await apiFetch(`/conversations/${convId}`)
      if (!r.ok) return []
      const data = await r.json()
      if (data.error) return []
      return (data.messages || []).map((m: Record<string, unknown>) => ({
        role: m.role as string,
        content: m.content as string,
        model_label: m.model_label || undefined,
        model_key: m.model_label ? 'system' : undefined,
        elapsed_seconds: m.elapsed_seconds as number | undefined,
        tool_calls: (m.tool_calls as unknown[]) || [],
        plan: m.plan || null,
        error: false,
      }))
    } catch (e) { console.error('[useApi] Load messages failed:', e); return [] }
  }, [])

  const deleteConversation = useCallback(async (convId: string) => {
    try {
      await apiFetch(`/conversations/${convId}`, { method: 'DELETE' })
      setConversations(prev => prev.filter(c => c.id !== convId))
      return true
    } catch (e) { console.error('[useApi] Delete conversation failed:', e); return false }
  }, [])

  // Send query
  const sendQuery = useCallback(async (query: string, conversationId?: string, history?: ChatMessage[]) => {
    const body: Record<string, unknown> = { query }
    if (conversationId) body.conversation_id = conversationId
    else if (history) {
      body.history = history.filter(m => m.role !== 'notification').map(m => ({ role: m.role, content: m.content }))
    }
    const r = await apiFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`Query failed: ${r.status}`)
    return await r.json()
  }, [])

  // Tasks
  const loadTasks = useCallback(async () => {
    try {
      const r = await apiFetch('/api/tasks')
      if (!r.ok) return
      const data = await r.json()
      if (Array.isArray(data)) setTasks(data)
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [])

  const launchTask = useCallback(async (description: string) => {
    try {
      await apiFetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      })
      loadTasks()
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [loadTasks])

  const cancelTask = useCallback(async (taskId: string) => {
    try {
      await apiFetch(`/api/task/${taskId}`, { method: 'DELETE' })
      loadTasks()
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [loadTasks])

  // Briefings
  const loadBriefings = useCallback(async () => {
    try {
      const r = await apiFetch('/api/briefings')
      if (!r.ok) return
      const data = await r.json()
      if (Array.isArray(data)) setBriefings(data)
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [])

  const markBriefingRead = useCallback(async (briefingId: string) => {
    try {
      await apiFetch(`/api/briefings/${briefingId}/read`, { method: 'POST' })
      setBriefings(prev => prev.map(b => b.id === briefingId ? { ...b, read: true } : b))
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [])

  const markAllBriefingsRead = useCallback(async () => {
    const unread = briefings.filter(b => !b.read)
    for (const b of unread) {
      try { await apiFetch(`/api/briefings/${b.id}/read`, { method: 'POST' }) } catch (e) { console.error('[useApi] Error:', e) }
    }
    setBriefings(prev => prev.map(b => ({ ...b, read: true })))
  }, [briefings])

  // Send message (REST with conversation_id, streams via WS)
  const sendMessage = useCallback(async (query: string, conversationId: string) => {
    const r = await apiFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, conversation_id: conversationId }),
    })
    if (!r.ok) throw new Error(`Message failed: ${r.status}`)
    return await r.json()
  }, [])

  // Post to channel as operator
  const postToChannel = useCallback(async (channel: string, content: string) => {
    try {
      const r = await apiFetch('/api/channels/post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel, content, sender: 'operator' }),
      })
      return r.ok
    } catch { return false }
  }, [])

  // Agents
  const loadAgents = useCallback(async () => {
    try {
      const r = await apiFetch('/api/agents')
      if (r.ok) return await r.json()
    } catch (e) { console.error('[useApi] Error:', e) }
    return []
  }, [])

  // Upload file
  const uploadFile = useCallback(async (file: File, onProgress?: (pct: number) => void): Promise<{ filename: string; url: string } | null> => {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest()
      const formData = new FormData()
      formData.append('file', file)

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
        })
      }

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          try { resolve(JSON.parse(xhr.responseText)) } catch { resolve(null) }
        } else resolve(null)
      })
      xhr.addEventListener('error', () => resolve(null))

      xhr.open('POST', apiUrl('/api/upload'))
      const key = getApiKey()
      if (key) xhr.setRequestHeader('X-API-Key', key)
      xhr.send(formData)
    })
  }, [])

  // Memory
  const searchMemory = useCallback(async (query: string, topK = 20): Promise<MemorySearchResult[]> => {
    try {
      const r = await apiFetch(`/api/memory?q=${encodeURIComponent(query)}&top_k=${topK}`)
      if (!r.ok) return []
      return await r.json()
    } catch { return [] }
  }, [])

  const getMemoryCount = useCallback(async () => {
    try {
      const r = await apiFetch('/api/memory')
      if (!r.ok) return
      const data = await r.json()
      setMemoryCount(data.count ?? 0)
    } catch (e) { console.error('[useApi] Error:', e) }
  }, [])

  // Poll memory count every 30s
  useEffect(() => {
    getMemoryCount()
    const id = setInterval(getMemoryCount, 30000)
    return () => clearInterval(id)
  }, [getMemoryCount])

  // Load on mount + periodic refresh
  useEffect(() => {
    loadConversations()
    loadTasks()
    loadBriefings()
  }, [loadConversations, loadTasks, loadBriefings])

  useEffect(() => {
    const id = setInterval(() => { loadTasks(); loadBriefings() }, 10000)
    return () => clearInterval(id)
  }, [loadTasks, loadBriefings])

  return {
    apiUp, modelStatus, conversations, tasks, briefings,
    loadConversations, createConversation, loadConversationMessages, deleteConversation,
    sendQuery, sendMessage, postToChannel, loadTasks, launchTask, cancelTask,
    loadBriefings, markBriefingRead, markAllBriefingsRead,
    loadAgents, uploadFile,
    searchMemory, getMemoryCount, memoryCount,
  }
}
