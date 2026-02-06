import { useState, useCallback, useRef, useEffect } from 'react'
import { useApi } from './useApi'
import type { ChatMessage, Conversation } from '../types'

export function useChat() {
  const api = useApi()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [activeConvoId, setActiveConvoId] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const scrollToEnd = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToEnd() }, [messages, scrollToEnd])

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages(prev => [...prev, msg])
  }, [])

  const setAllMessages = useCallback((msgs: ChatMessage[]) => {
    setMessages(msgs)
  }, [])

  const handleStreamChunk = useCallback((data: Record<string, unknown>) => {
    const content = data.content as string
    setMessages(prev => {
      const last = prev[prev.length - 1]
      if (last && last.role === 'assistant' && last._streaming) {
        return [...prev.slice(0, -1), { ...last, content: last.content + content }]
      }
      return [...prev, { role: 'assistant', content, _streaming: true, model_key: 'system' }]
    })
  }, [])

  const handleChatMessage = useCallback((data: Record<string, unknown>) => {
    addMessage({
      role: data.role as 'user' | 'assistant',
      content: data.content as string,
      model_key: data.model_key as string | undefined,
      model_label: data.model_label as string | undefined,
    })
  }, [addMessage])

  const loadConversation = useCallback(async (convId: string) => {
    setLoading(true)
    const msgs = await api.loadConversationMessages(convId)
    setAllMessages(msgs)
    setActiveConvoId(convId)
    setLoading(false)
  }, [api, setAllMessages])

  const createConversation = useCallback(async () => {
    const conv = await api.createConversation()
    if (conv) {
      setAllMessages([])
      setActiveConvoId(conv.id)
      return conv
    }
    return null
  }, [api, setAllMessages])

  const deleteConversation = useCallback(async (convId: string) => {
    await api.deleteConversation(convId)
    if (activeConvoId === convId) {
      setAllMessages([])
      setActiveConvoId(null)
    }
  }, [api, activeConvoId, setAllMessages])

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || sending) return

    // Ensure we have an active conversation
    let convId = activeConvoId
    if (!convId) {
      const conv = await api.createConversation()
      if (!conv) return
      convId = conv.id
      setActiveConvoId(convId)
    }

    // Add user message to UI
    addMessage({ role: 'user', content: text })
    setSending(true)

    try {
      const result = await api.sendMessage(text, convId)
      // Replace streaming message with final result
      setMessages(prev => {
        const filtered = prev.filter(m => !m._streaming)
        return [...filtered, {
          role: 'assistant' as const,
          content: result.content || result.response || 'No response.',
          model_key: result.model_key,
          model_label: result.model_label,
          elapsed_seconds: result.elapsed_seconds,
          tool_calls: result.tool_calls,
          plan: result.plan,
        }]
      })
      // Refresh conversation list
      api.loadConversations()
    } catch (e) {
      addMessage({ role: 'assistant', content: 'Error: Failed to get response.', error: true })
    } finally {
      setSending(false)
    }
  }, [activeConvoId, sending, api, addMessage])

  return {
    messages,
    activeConvoId,
    sending,
    loading,
    endRef,
    conversations: api.conversations,
    addMessage,
    setAllMessages,
    handleStreamChunk,
    handleChatMessage,
    sendMessage,
    loadConversation,
    createConversation,
    deleteConversation,
    loadConversations: api.loadConversations,
  }
}
