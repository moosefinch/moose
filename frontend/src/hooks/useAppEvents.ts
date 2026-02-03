import { useEffect, useRef } from 'react'
import type { AgentEvent, AgentState, Mission, ChannelMessage, CognitiveStatus, ChatMessage } from '../types'

interface AppEventsConfig {
  on: (type: string, handler: (data: Record<string, unknown>) => void) => void
  off: (type: string, handler: (data: Record<string, unknown>) => void) => void
  chat: {
    addMessage: (msg: ChatMessage) => void
    handleStreamChunk: (data: Record<string, unknown>) => void
    handleChatMessage: (data: Record<string, unknown>) => void
  }
  api: {
    loadTasks: () => void
    loadBriefings: () => void
    briefings: { id: string; read: boolean; content: string }[]
    tasks: { id: string; status: string; description: string }[]
  }
  marketing: { refresh: () => void }
  setActiveModel: (model: string) => void
  setAgentEvents: React.Dispatch<React.SetStateAction<AgentEvent[]>>
  setAgentStates: React.Dispatch<React.SetStateAction<AgentState[]>>
  setActiveMission: React.Dispatch<React.SetStateAction<Mission | null>>
  setChannelMessages: React.Dispatch<React.SetStateAction<ChannelMessage[]>>
  setCognitiveStatus: React.Dispatch<React.SetStateAction<CognitiveStatus | null>>
  setPendingApproval: React.Dispatch<React.SetStateAction<{ id: string; action: string; description: string; params: Record<string, unknown> } | null>>
  addToast: (content: string, opts?: { type?: 'default' | 'ai' | 'success' | 'error'; duration?: number }) => void
}

export function useAppEvents(cfg: AppEventsConfig) {
  const {
    on, off, chat, api, marketing,
    setActiveModel, setAgentEvents, setActiveMission,
    setChannelMessages, setCognitiveStatus, setPendingApproval,
    addToast,
  } = cfg

  useEffect(() => {
    const handleNotification = (data: Record<string, unknown>) => {
      chat.addMessage({ role: 'notification', content: data.message as string })
    }

    const handleExecStatus = (data: Record<string, unknown>) => {
      if (data.model) setActiveModel(data.model as string)
    }

    const handleAgentEvent = (data: Record<string, unknown>) => {
      const evt: AgentEvent = {
        id: crypto.randomUUID(),
        time: new Date().toISOString(),
        eventType: (data.event_type || data.event || 'unknown') as string,
        agent: (data.agent || data.agent_name || '') as string,
        detail: (data.detail || data.message || data.description || '') as string,
        from_model: (data.from_model || '') as string,
        to_model: (data.to_model || '') as string,
        tool: (data.tool || '') as string,
        args_preview: (data.args_preview || '') as string,
        task_preview: (data.task_preview || '') as string,
        target: (data.target || '') as string,
      }
      setAgentEvents(prev => [evt, ...prev].slice(0, 200))
      if (data.model) setActiveModel(data.model as string)
    }

    const handleAgentMessage = (data: Record<string, unknown>) => {
      const evt: AgentEvent = {
        id: crypto.randomUUID(),
        time: new Date().toISOString(),
        eventType: 'message',
        agent: (data.sender || '') as string,
        target: (data.recipient || '') as string,
        detail: (data.preview || data.content || '') as string,
        msgType: (data.message_type || data.msg_type || '') as string,
      }
      setAgentEvents(prev => [evt, ...prev].slice(0, 200))
    }

    const handleMissionUpdate = (data: Record<string, unknown>) => {
      setActiveMission({
        mission_id: data.mission_id as string,
        status: data.status as string,
        completed: (data.completed || 0) as number,
        total: (data.total || 0) as number,
        active_agent: (data.active_agent || '') as string,
      })
      const evt: AgentEvent = {
        id: crypto.randomUUID(),
        time: new Date().toISOString(),
        eventType: 'mission_update',
        agent: (data.active_agent || '') as string,
        detail: `Mission: ${data.completed || 0}/${data.total || 0} tasks complete`,
      }
      setAgentEvents(prev => [evt, ...prev].slice(0, 200))
    }

    const handleChannelMessage = (data: Record<string, unknown>) => {
      const msg: ChannelMessage = {
        id: data.id as string || Date.now().toString(),
        channel: data.channel as string || '',
        sender: data.sender as string || '',
        content: data.content as string || '',
        timestamp: data.timestamp as string || new Date().toISOString(),
      }
      setChannelMessages(prev => [...prev, msg].slice(-500))
    }

    const handleApprovalRequest = (data: Record<string, unknown>) => {
      setPendingApproval({
        id: data.id as string,
        action: data.action as string,
        description: data.description as string,
        params: (data.params || {}) as Record<string, unknown>,
      })
    }

    const handleLeadReceived = (data: Record<string, unknown>) => {
      const lead = (data.lead || {}) as Record<string, unknown>
      const name = (lead.name || 'Unknown') as string
      const company = (lead.company || '') as string
      const toastContent = `New lead: ${name}${company ? ` from ${company}` : ''}`
      addToast(toastContent)
      chat.addMessage({ role: 'notification', content: `[Inbound Lead] ${toastContent}` })
    }

    const handleMarketingNotification = (data: Record<string, unknown>) => {
      const msg = (data.message || 'New marketing activity') as string
      addToast(msg)
      marketing.refresh()
    }

    const handleMarketingApproval = () => {
      marketing.refresh()
    }

    const handleProactiveInsight = (data: Record<string, unknown>) => {
      const message = (data.message || '') as string
      const category = (data.category || 'observation') as string
      chat.addMessage({ role: 'proactive', content: message, proactive_category: category })
      addToast(message.slice(0, 100), { type: 'ai', duration: 8000 })
    }

    const handleCognitiveStatus = (data: Record<string, unknown>) => {
      setCognitiveStatus({
        phase: (data.phase || 'idle') as CognitiveStatus['phase'],
        cycle: (data.cycle || 0) as number,
        observations: (data.observations || 0) as number,
        thoughts: (data.thoughts || 0) as number,
      })
    }

    const handleBriefingReady = (data: Record<string, unknown>) => {
      const briefing = data.briefing as Record<string, unknown> | undefined
      if (briefing) {
        const content = (briefing.content || '') as string
        chat.addMessage({ role: 'notification', content: `[Briefing] ${content.slice(0, 500)}` })
        addToast('New briefing ready')
      }
      api.loadBriefings()
    }

    const handleContentDrafted = (data: Record<string, unknown>) => {
      const title = (data.title || 'New content') as string
      const platform = (data.platform || '') as string
      addToast(`Content drafted: ${title} (${platform})`)
      marketing.refresh()
    }

    on('proactive_insight', handleProactiveInsight)
    on('cognitive_status', handleCognitiveStatus)
    on('briefing_ready', handleBriefingReady)
    on('content_drafted', handleContentDrafted)
    on('marketing_notification', handleMarketingNotification)
    on('marketing_approval_resolved', handleMarketingApproval)
    on('approval_request', handleApprovalRequest)
    on('lead_received', handleLeadReceived)
    on('notification', handleNotification)
    on('stream_chunk', chat.handleStreamChunk)
    on('execution_status', handleExecStatus)
    on('agent_event', handleAgentEvent)
    on('agent_message', handleAgentMessage)
    on('mission_update', handleMissionUpdate)
    on('task_update', () => api.loadTasks())
    on('briefing', () => api.loadBriefings())
    on('chat_message', chat.handleChatMessage)
    on('channel_message', handleChannelMessage)

    return () => {
      off('proactive_insight', handleProactiveInsight)
      off('cognitive_status', handleCognitiveStatus)
      off('briefing_ready', handleBriefingReady)
      off('content_drafted', handleContentDrafted)
      off('marketing_notification', handleMarketingNotification)
      off('marketing_approval_resolved', handleMarketingApproval)
      off('approval_request', handleApprovalRequest)
      off('lead_received', handleLeadReceived)
      off('notification', handleNotification)
      off('stream_chunk', chat.handleStreamChunk)
      off('execution_status', handleExecStatus)
      off('agent_event', handleAgentEvent)
      off('agent_message', handleAgentMessage)
      off('mission_update', handleMissionUpdate)
      off('chat_message', chat.handleChatMessage)
      off('channel_message', handleChannelMessage)
    }
  }, [on, off, chat.addMessage, chat.handleStreamChunk, chat.handleChatMessage, api, marketing.refresh, addToast])

  // Briefing toast detection
  const briefingIdsRef = useRef(new Set<string>())
  useEffect(() => {
    for (const b of api.briefings) {
      if (!b.read && !briefingIdsRef.current.has(b.id)) {
        briefingIdsRef.current.add(b.id)
        chat.addMessage({ role: 'notification', content: `[Briefing] ${b.content.slice(0, 200)}${b.content.length > 200 ? '...' : ''}` })
      }
    }
  }, [api.briefings, chat.addMessage])

  // Completed task notifications
  const completedTaskIdsRef = useRef(new Set<string>())
  useEffect(() => {
    for (const t of api.tasks) {
      if (t.status === 'completed' && !completedTaskIdsRef.current.has(t.id)) {
        completedTaskIdsRef.current.add(t.id)
        chat.addMessage({ role: 'notification', content: `[Proactive] Task completed: ${t.description}` })
      }
    }
  }, [api.tasks, chat.addMessage])
}
