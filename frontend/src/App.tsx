import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigation, type Page } from './contexts/NavigationContext'
import { useToast } from './contexts/ToastContext'
import { TabBar } from './components/navigation/TabBar'
import { DashboardPage } from './pages/DashboardPage'
import { ViewportPage } from './pages/ViewportPage'
import { PrinterPage } from './pages/PrinterPage'
import { MorePage } from './pages/MorePage'
import { AIToast } from './components/ambient/AIToast'
import { AmbientIndicator } from './components/ambient/AmbientIndicator'
import { VoiceFAB } from './components/ambient/VoiceFAB'
import { ApprovalDialog } from './components/ApprovalDialog'
import { VoiceModeOverlay } from './components/VoiceModeOverlay'
import { useWebSocket } from './hooks/useWebSocket'
import { useApi } from './hooks/useApi'
import { useChat } from './hooks/useChat'
import { useMarketing } from './hooks/useMarketing'
import { useScheduledJobs } from './hooks/useScheduledJobs'
import { useVoice } from './hooks/useVoice'
import { useWebhooks } from './hooks/useWebhooks'
import { useAppEvents } from './hooks/useAppEvents'
import { useConfig } from './contexts/ConfigContext'
import type { AgentEvent, AgentState, Mission, ChannelMessage, CognitiveStatus } from './types'

export function App() {
  const config = useConfig()
  const { page, setPage, navigateTo } = useNavigation()
  const { toasts, addToast, dismissToast } = useToast()

  const [activeModel, setActiveModel] = useState('')
  const [thinkingElapsed, setThinkingElapsed] = useState(0)
  const [agentStates, setAgentStates] = useState<AgentState[]>([])
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([])
  const [activeMission, setActiveMission] = useState<Mission | null>(null)
  const [channelMessages, setChannelMessages] = useState<ChannelMessage[]>([])
  const [cognitiveStatus, setCognitiveStatus] = useState<CognitiveStatus | null>(null)
  const [pendingApproval, setPendingApproval] = useState<{id: string; action: string; description: string; params: Record<string, unknown>} | null>(null)
  const [expandedIndicator, setExpandedIndicator] = useState(false)
  const [voiceOverlayOpen, setVoiceOverlayOpen] = useState(false)

  const { connected, on, off } = useWebSocket()
  const api = useApi()
  const chat = useChat()
  const marketing = useMarketing()
  const scheduling = useScheduledJobs()
  const webhooks = useWebhooks()
  const voice = useVoice()

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

  // Agent polling
  useEffect(() => {
    const poll = async () => {
      const agents = await api.loadAgents()
      if (agents && agents.length > 0) setAgentStates(agents)
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [api])

  // WebSocket event wiring (extracted)
  useAppEvents({
    on, off, chat, api, marketing,
    setActiveModel, setAgentEvents, setAgentStates,
    setActiveMission, setChannelMessages, setCognitiveStatus,
    setPendingApproval, addToast,
  })

  // Keyboard shortcuts: Cmd+1-4 for page switching
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        const pageMap: Record<string, Page> = { '1': 'dashboard', '2': 'viewport', '3': 'printer', '4': 'more' }
        if (pageMap[e.key]) {
          e.preventDefault()
          setPage(pageMap[e.key])
          return
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
  }, [setPage, voiceOverlayOpen, voice.startRecording])

  // Close ambient dropdown on outside click
  useEffect(() => {
    if (!expandedIndicator) return
    const close = () => setExpandedIndicator(false)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [expandedIndicator])

  const handleVoiceStart = useCallback(() => {
    setVoiceOverlayOpen(true)
    voice.startRecording()
  }, [voice])

  return (
    <>
      <AIToast toasts={toasts} onDismiss={dismissToast} />

      <div className="app-shell">
        <TabBar connected={connected} apiUp={api.apiUp} cognitiveStatus={cognitiveStatus} />

        <div className="page-container">
          {page === 'dashboard' && (
            <DashboardPage
              agentEvents={agentEvents}
              agentStates={agentStates}
              briefings={api.briefings}
              tasks={api.tasks}
              onLaunchTask={api.launchTask}
              onNavigateViewport={() => setPage('viewport')}
            />
          )}

          {page === 'viewport' && <ViewportPage />}

          {page === 'printer' && <PrinterPage />}

          {page === 'more' && (
            <MorePage
              messages={chat.messages}
              sending={chat.sending}
              loading={chat.loading}
              activeModel={activeModel}
              thinkingElapsed={thinkingElapsed}
              endRef={chat.endRef}
              onSend={chat.sendMessage}
              onVoiceStart={handleVoiceStart}
              conversations={chat.conversations}
              activeConvoId={chat.activeConvoId}
              onSelectConversation={chat.loadConversation}
              onNewConversation={chat.createConversation}
              onDeleteConversation={chat.deleteConversation}
              agents={agentStates}
              connected={connected}
              apiUp={api.apiUp}
              channelMessages={channelMessages}
              onPostMessage={api.postToChannel}
              memoryCount={api.memoryCount}
              onSearchMemory={api.searchMemory}
              crmEnabled={config.enabledPlugins.includes('crm')}
              pendingEmails={marketing.pendingEmails}
              pendingContent={marketing.pendingContent}
              marketingStats={marketing.stats}
              onApproveEmail={marketing.approveEmail}
              onRejectEmail={marketing.rejectEmail}
              onApproveContent={marketing.approveContent}
              onRejectContent={marketing.rejectContent}
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
          )}
        </div>
      </div>

      <AmbientIndicator
        cognitiveStatus={cognitiveStatus}
        agents={agentStates}
        expanded={expandedIndicator}
        onToggle={() => setExpandedIndicator(p => !p)}
      />

      <VoiceFAB
        isRecording={voice.isRecording}
        onStart={handleVoiceStart}
        onStop={async () => {
          const text = await voice.stopRecording()
          setVoiceOverlayOpen(false)
          if (text.trim()) chat.sendMessage(text)
        }}
      />

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
