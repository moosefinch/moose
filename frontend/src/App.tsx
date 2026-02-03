import { useState, useEffect, useRef, useCallback } from 'react'
import { Sidebar } from './components/Sidebar'
import { StatusBar } from './components/StatusBar'
import { ChatPanel } from './components/ChatPanel'
import { ChannelsDrawer } from './components/ChannelsDrawer'
import { MemoryExplorer } from './components/MemoryExplorer'
import { MarketingDrawer } from './components/MarketingDrawer'
import { SchedulingDrawer } from './components/SchedulingDrawer'
import { PluginsPanel } from './components/PluginsPanel'
import { Toast } from './components/Toast'
import { ApprovalDialog } from './components/ApprovalDialog'
import { useWebSocket } from './hooks/useWebSocket'
import { useApi } from './hooks/useApi'
import { useChat } from './hooks/useChat'
import { useMarketing } from './hooks/useMarketing'
import { useScheduledJobs } from './hooks/useScheduledJobs'
import { useVoice } from './hooks/useVoice'
import { useWebhooks } from './hooks/useWebhooks'
import { VoiceModeOverlay } from './components/VoiceModeOverlay'
import { apiUrl } from './api'
import { useConfig } from './contexts/ConfigContext'
import type { AgentEvent, AgentState, Mission, ChannelMessage, CognitiveStatus } from './types'

export function App() {
  const config = useConfig()
  const [activeModel, setActiveModel] = useState('')
  const [thinkingElapsed, setThinkingElapsed] = useState(0)

  // Agent state
  const [agentStates, setAgentStates] = useState<AgentState[]>([])
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([])
  const [activeMission, setActiveMission] = useState<Mission | null>(null)

  // Toast
  const [toasts, setToasts] = useState<{ id: string; content: string }[]>([])

  // Channels
  const [channelMessages, setChannelMessages] = useState<ChannelMessage[]>([])

  // Sidebar
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Drawers
  const [channelsDrawerOpen, setChannelsDrawerOpen] = useState(false)
  const [memoryExplorerOpen, setMemoryExplorerOpen] = useState(false)
  const [marketingDrawerOpen, setMarketingDrawerOpen] = useState(false)
  const [schedulingDrawerOpen, setSchedulingDrawerOpen] = useState(false)
  const [pluginsPanelOpen, setPluginsPanelOpen] = useState(false)

  // Marketing hook
  const marketing = useMarketing()

  // Scheduling hook
  const scheduling = useScheduledJobs()

  // Webhooks hook
  const webhooks = useWebhooks()

  // Voice hook
  const voice = useVoice()
  const [voiceOverlayOpen, setVoiceOverlayOpen] = useState(false)

  // Cognitive loop status
  const [cognitiveStatus, setCognitiveStatus] = useState<CognitiveStatus | null>(null)

  // Desktop approval
  const [pendingApproval, setPendingApproval] = useState<{id: string, action: string, description: string, params: Record<string, unknown>} | null>(null)

  // Hooks
  const { connected, on, off } = useWebSocket()
  const api = useApi()
  const chat = useChat()

  const thinkingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Thinking timer
  useEffect(() => {
    if (chat.sending) {
      setThinkingElapsed(0)
      thinkingTimerRef.current = setInterval(() => setThinkingElapsed(prev => prev + 1), 1000)
    } else {
      if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current)
      setThinkingElapsed(0)
    }
    return () => { if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current) }
  }, [chat.sending])

  // Agent polling — 5s interval
  useEffect(() => {
    const poll = async () => {
      const agents = await api.loadAgents()
      if (agents && agents.length > 0) setAgentStates(agents)
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [api])

  // WebSocket event handlers
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
      const toastId = `lead-${Date.now()}`
      setToasts(prev => [...prev, { id: toastId, content: toastContent }])
      setTimeout(() => setToasts(t => t.filter(x => x.id !== toastId)), 8000)
      chat.addMessage({ role: 'notification', content: `[Inbound Lead] ${toastContent}` })
    }

    const handleMarketingNotification = (data: Record<string, unknown>) => {
      const msg = (data.message || 'New marketing activity') as string
      const toastId = `mkt-${Date.now()}`
      setToasts(prev => [...prev, { id: toastId, content: msg }])
      setTimeout(() => setToasts(t => t.filter(x => x.id !== toastId)), 6000)
      marketing.refresh()
    }

    const handleMarketingApproval = () => {
      marketing.refresh()
    }

    const handleProactiveInsight = (data: Record<string, unknown>) => {
      const message = (data.message || '') as string
      const category = (data.category || 'observation') as string
      const urgency = (data.urgency || 0.5) as number

      // Add as proactive message in chat
      chat.addMessage({
        role: 'proactive',
        content: message,
        proactive_category: category,
      })

      // Toast notification
      const toastId = `proactive-${Date.now()}`
      setToasts(prev => [...prev, { id: toastId, content: message.slice(0, 100) }])
      setTimeout(() => setToasts(t => t.filter(x => x.id !== toastId)), 6000)
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

        const toastId = `briefing-${Date.now()}`
        setToasts(prev => [...prev, { id: toastId, content: 'New briefing ready' }])
        setTimeout(() => setToasts(t => t.filter(x => x.id !== toastId)), 6000)
      }
      api.loadBriefings()
    }

    const handleContentDrafted = (data: Record<string, unknown>) => {
      const title = (data.title || 'New content') as string
      const platform = (data.platform || '') as string
      const toastId = `content-${Date.now()}`
      setToasts(prev => [...prev, { id: toastId, content: `Content drafted: ${title} (${platform})` }])
      setTimeout(() => setToasts(t => t.filter(x => x.id !== toastId)), 6000)
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
  }, [on, off, chat.addMessage, chat.handleStreamChunk, chat.handleChatMessage, api, marketing.refresh])

  // Briefing toast detection
  useEffect(() => {
    const newUnread = api.briefings.filter(b => !b.read)
    if (newUnread.length > 0) {
      setToasts(prev => {
        const existingIds = new Set(prev.map(t => t.id))
        const fresh = newUnread.filter(b => !existingIds.has(b.id)).slice(0, 3)
        if (fresh.length === 0) return prev
        setTimeout(() => {
          setToasts(t => t.filter(toast => !fresh.find(n => n.id === toast.id)))
        }, 6000)
        return [...prev, ...fresh.map(b => ({ id: b.id, content: b.content }))]
      })
    }
  }, [api.briefings])

  // Inject briefing notifications into chat
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

  // Drawer callbacks
  const openChannels = useCallback(() => setChannelsDrawerOpen(true), [])
  const closeChannels = useCallback(() => setChannelsDrawerOpen(false), [])
  const openMemory = useCallback(() => setMemoryExplorerOpen(true), [])
  const closeMemory = useCallback(() => setMemoryExplorerOpen(false), [])
  const openMarketing = useCallback(() => setMarketingDrawerOpen(true), [])
  const closeMarketing = useCallback(() => setMarketingDrawerOpen(false), [])
  const openScheduling = useCallback(() => setSchedulingDrawerOpen(true), [])
  const closeScheduling = useCallback(() => setSchedulingDrawerOpen(false), [])
  const openPlugins = useCallback(() => setPluginsPanelOpen(true), [])
  const closePlugins = useCallback(() => setPluginsPanelOpen(false), [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        if (e.key === '\\') {
          e.preventDefault()
          setSidebarOpen(prev => !prev)
        }
        if (e.key === 'k') {
          e.preventDefault()
          setSidebarOpen(true) // Focus sidebar / new conversation
        }
        if (e.key === 'j') {
          e.preventDefault()
          setChannelsDrawerOpen(prev => !prev)
          setMemoryExplorerOpen(false)
          setMarketingDrawerOpen(false)
        }
        if (e.key === 'm') {
          e.preventDefault()
          setMemoryExplorerOpen(prev => !prev)
          setChannelsDrawerOpen(false)
          setMarketingDrawerOpen(false)
        }
        if (e.key === 'p') {
          e.preventDefault()
          setMarketingDrawerOpen(prev => !prev)
          setChannelsDrawerOpen(false)
          setMemoryExplorerOpen(false)
          setSchedulingDrawerOpen(false)
        }
        if (e.key === 's' && e.shiftKey) {
          e.preventDefault()
          setSchedulingDrawerOpen(prev => !prev)
          setChannelsDrawerOpen(false)
          setMemoryExplorerOpen(false)
          setMarketingDrawerOpen(false)
        }
        if (e.key === 'v' && e.shiftKey) {
          e.preventDefault()
          if (!voiceOverlayOpen) {
            setVoiceOverlayOpen(true)
            voice.startRecording()
          }
        }
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  const activeConvoTitle = chat.conversations.find(c => c.id === chat.activeConvoId)?.title

  return (
    <>
      <Toast toasts={toasts} onDismiss={(id) => setToasts(t => t.filter(x => x.id !== id))} />

      <div className="app-layout">
        <Sidebar
          open={sidebarOpen}
          onToggle={() => setSidebarOpen(p => !p)}
          conversations={chat.conversations}
          activeConvoId={chat.activeConvoId}
          onSelectConversation={chat.loadConversation}
          onNewConversation={chat.createConversation}
          onDeleteConversation={chat.deleteConversation}
          agents={agentStates}
          connected={connected}
          apiUp={api.apiUp}
          pendingMarketing={config.enabledPlugins.includes('crm') ? marketing.totalPending : 0}
          onOpenMarketing={config.enabledPlugins.includes('crm') ? openMarketing : () => {}}
          onOpenChannels={openChannels}
          onOpenMemory={openMemory}
          onOpenScheduling={openScheduling}
          onOpenPlugins={openPlugins}
          cognitiveStatus={cognitiveStatus}
        />
        <div className="main-content">
          <StatusBar
            sidebarOpen={sidebarOpen}
            onToggleSidebar={() => setSidebarOpen(p => !p)}
            activeConvoTitle={activeConvoTitle}
            connected={connected}
            apiUp={api.apiUp}
          />
          <ChatPanel
            messages={chat.messages}
            sending={chat.sending}
            loading={chat.loading}
            activeModel={activeModel}
            thinkingElapsed={thinkingElapsed}
            endRef={chat.endRef}
            onSend={chat.sendMessage}
            onVoiceStart={() => {
              setVoiceOverlayOpen(true)
              voice.startRecording()
            }}
          />
        </div>
      </div>

      <ChannelsDrawer
        open={channelsDrawerOpen}
        onClose={closeChannels}
        messages={channelMessages}
        onPostMessage={api.postToChannel}
      />

      <MemoryExplorer
        open={memoryExplorerOpen}
        onClose={closeMemory}
        memoryCount={api.memoryCount}
        onSearch={api.searchMemory}
      />

      {config.enabledPlugins.includes('crm') && (
        <MarketingDrawer
          open={marketingDrawerOpen}
          onClose={closeMarketing}
          pendingEmails={marketing.pendingEmails}
          pendingContent={marketing.pendingContent}
          stats={marketing.stats}
          onApproveEmail={marketing.approveEmail}
          onRejectEmail={marketing.rejectEmail}
          onEditEmail={() => {}}
          onApproveContent={marketing.approveContent}
          onRejectContent={marketing.rejectContent}
        />
      )}

      <SchedulingDrawer
        open={schedulingDrawerOpen}
        onClose={closeScheduling}
        jobs={scheduling.jobs}
        onCreateJob={scheduling.createJob}
        onUpdateJob={scheduling.updateJob}
        onDeleteJob={scheduling.deleteJob}
        onParseNatural={scheduling.parseNatural}
        webhooks={webhooks.webhooks}
        onCreateWebhook={webhooks.createWebhook}
        onUpdateWebhook={webhooks.updateWebhook}
        onDeleteWebhook={webhooks.deleteWebhook}
      />

      <PluginsPanel open={pluginsPanelOpen} onClose={closePlugins} />

      <ApprovalDialog approval={pendingApproval} onResolved={() => setPendingApproval(null)} />

      <VoiceModeOverlay
        open={voiceOverlayOpen}
        isRecording={voice.isRecording}
        isTranscribing={voice.isTranscribing}
        onStop={async () => {
          const text = await voice.stopRecording()
          setVoiceOverlayOpen(false)
          if (text.trim()) chat.sendMessage(text)
        }}
        onCancel={() => {
          voice.stopRecording()
          setVoiceOverlayOpen(false)
        }}
      />
    </>
  )
}
