import { useNavigation, type MoreSubPage } from '../contexts/NavigationContext'
import { Sidebar } from '../components/Sidebar'
import { ChatPanel } from '../components/ChatPanel'
import { ChannelsDrawer } from '../components/ChannelsDrawer'
import { MemoryExplorer } from '../components/MemoryExplorer'
import { MarketingDrawer } from '../components/MarketingDrawer'
import { SchedulingDrawer } from '../components/SchedulingDrawer'
import { PluginsPanel } from '../components/PluginsPanel'
import { AdvocacyPanel } from '../components/AdvocacyPanel'
import { PrinterPage } from './PrinterPage'
import { ProposalsHistoryPanel } from '../components/ProposalsHistoryPanel'
import type { ChatMessage, AgentState, Briefing, ChannelMessage, PendingEmail, ContentDraft, MarketingStats, ScheduledJob, WebhookEndpoint, CognitiveStatus, AdvocacyGoal, AdvocacyPattern, AdvocacyStatus, ImprovementProposal } from '../types'

const SUB_TABS: { id: MoreSubPage; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'channels', label: 'Channels' },
  { id: 'memory', label: 'Memory' },
  { id: 'advocacy', label: 'Advocacy' },
  { id: 'proposals', label: 'Proposals' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'scheduling', label: 'Scheduling' },
  { id: 'plugins', label: 'Plugins' },
  { id: 'printer', label: '3D Printer' },
]

interface MorePageProps {
  // Chat
  messages: ChatMessage[]
  sending: boolean
  loading: boolean
  activeModel: string
  thinkingElapsed: number
  endRef: React.RefObject<HTMLDivElement | null>
  onSend: (msg: string) => void
  onVoiceStart: () => void
  isRecording?: boolean
  // Sidebar / Briefings
  briefings: Briefing[]
  onMarkBriefingRead: (id: string) => void
  onMarkAllRead: () => void
  agents: AgentState[]
  connected: boolean
  apiUp: boolean
  // Channels
  channelMessages: ChannelMessage[]
  onPostMessage: (channel: string, content: string) => Promise<boolean>
  // Memory
  memoryCount: number
  onSearchMemory: (q: string, topK?: number) => Promise<{ text: string; score: number }[]>
  // Advocacy
  advocacyEnabled: boolean
  advocacyStatus: AdvocacyStatus | null
  advocacyGoals: AdvocacyGoal[]
  advocacyUnconfirmedGoals: AdvocacyGoal[]
  advocacyPatterns: AdvocacyPattern[]
  onCreateGoal: (data: { text: string; category?: string; priority?: number }) => void
  onUpdateGoal: (id: string, data: { status?: string; priority?: number }) => void
  onConfirmGoal: (id: string) => void
  onRejectGoal: (id: string) => void
  onRecordEvidence: (id: string, data: { type?: string; description: string }) => void
  onDismissPattern: (id: string) => void
  onStartOnboarding: () => void
  onRespondOnboarding: (text: string) => Promise<{ next_prompt?: string; stage?: string; complete?: boolean } | null>
  onResetOnboarding: () => void
  // Marketing
  crmEnabled: boolean
  pendingEmails: PendingEmail[]
  pendingContent: ContentDraft[]
  marketingStats: MarketingStats | null
  onApproveEmail: (id: string) => void
  onRejectEmail: (id: string) => void
  onApproveContent: (id: string) => void
  onRejectContent: (id: string) => void
  // Cognitive
  cognitiveStatus: CognitiveStatus | null
  // Scheduling
  jobs: ScheduledJob[]
  onCreateJob: (data: { description: string; schedule_type: string; schedule_value: string }) => void
  onUpdateJob: (id: string, data: Record<string, unknown>) => void
  onDeleteJob: (id: string) => void
  onParseNatural: (text: string) => Promise<{ schedule_type: string; schedule_value: string } | null>
  webhooks: WebhookEndpoint[]
  onCreateWebhook: (wh: Record<string, unknown>) => void
  onUpdateWebhook: (id: string, wh: Record<string, unknown>) => void
  onDeleteWebhook: (id: string) => void
  // Proposals
  proposals: ImprovementProposal[]
  onApproveProposal: (id: string) => void
  onRejectProposal: (id: string) => void
}

export function MorePage(props: MorePageProps) {
  const { subPage, setSubPage } = useNavigation()

  return (
    <div className="page-more">
      <div className="more-sub-tabs">
        {SUB_TABS.filter(t => (t.id !== 'marketing' || props.crmEnabled) && (t.id !== 'advocacy' || props.advocacyEnabled)).map(tab => (
          <button
            key={tab.id}
            className={`more-sub-tab ${subPage === tab.id ? 'active' : ''}`}
            onClick={() => setSubPage(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="more-content">
        {subPage === 'chat' && (
          <div className="more-chat-layout">
            <Sidebar
              open={true}
              onToggle={() => {}}
              briefings={props.briefings}
              onMarkBriefingRead={props.onMarkBriefingRead}
              onMarkAllRead={props.onMarkAllRead}
              agents={props.agents}
              connected={props.connected}
              apiUp={props.apiUp}
              pendingMarketing={0}
              onOpenMarketing={() => setSubPage('marketing')}
              onOpenChannels={() => setSubPage('channels')}
              onOpenMemory={() => setSubPage('memory')}
              onOpenScheduling={() => setSubPage('scheduling')}
              onOpenPlugins={() => setSubPage('plugins')}
              cognitiveStatus={null}
            />
            <ChatPanel
              messages={props.messages}
              sending={props.sending}
              loading={props.loading}
              activeModel={props.activeModel}
              thinkingElapsed={props.thinkingElapsed}
              endRef={props.endRef}
              onSend={props.onSend}
              onVoiceStart={props.onVoiceStart}
              isRecording={props.isRecording}
              cognitiveStatus={props.cognitiveStatus}
            />
          </div>
        )}

        {subPage === 'channels' && (
          <ChannelsDrawer
            open={true}
            onClose={() => setSubPage('chat')}
            messages={props.channelMessages}
            onPostMessage={props.onPostMessage}
            embedded
          />
        )}

        {subPage === 'memory' && (
          <MemoryExplorer
            open={true}
            onClose={() => setSubPage('chat')}
            memoryCount={props.memoryCount}
            onSearch={props.onSearchMemory}
            embedded
          />
        )}

        {subPage === 'advocacy' && props.advocacyEnabled && (
          <AdvocacyPanel
            open={true}
            onClose={() => setSubPage('chat')}
            status={props.advocacyStatus}
            goals={props.advocacyGoals}
            unconfirmedGoals={props.advocacyUnconfirmedGoals}
            patterns={props.advocacyPatterns}
            onCreateGoal={props.onCreateGoal}
            onUpdateGoal={props.onUpdateGoal}
            onConfirmGoal={props.onConfirmGoal}
            onRejectGoal={props.onRejectGoal}
            onRecordEvidence={props.onRecordEvidence}
            onDismissPattern={props.onDismissPattern}
            onStartOnboarding={props.onStartOnboarding}
            onRespondOnboarding={props.onRespondOnboarding}
            onResetOnboarding={props.onResetOnboarding}
            embedded
          />
        )}

        {subPage === 'proposals' && (
          <ProposalsHistoryPanel
            proposals={props.proposals}
            onApprove={props.onApproveProposal}
            onReject={props.onRejectProposal}
            onClose={() => setSubPage('chat')}
          />
        )}

        {subPage === 'marketing' && props.crmEnabled && (
          <MarketingDrawer
            open={true}
            onClose={() => setSubPage('chat')}
            pendingEmails={props.pendingEmails}
            pendingContent={props.pendingContent}
            stats={props.marketingStats}
            onApproveEmail={props.onApproveEmail}
            onRejectEmail={props.onRejectEmail}
            onEditEmail={() => {}}
            onApproveContent={props.onApproveContent}
            onRejectContent={props.onRejectContent}
            embedded
          />
        )}

        {subPage === 'scheduling' && (
          <SchedulingDrawer
            open={true}
            onClose={() => setSubPage('chat')}
            jobs={props.jobs}
            onCreateJob={props.onCreateJob}
            onUpdateJob={props.onUpdateJob}
            onDeleteJob={props.onDeleteJob}
            onParseNatural={props.onParseNatural}
            webhooks={props.webhooks}
            onCreateWebhook={props.onCreateWebhook}
            onUpdateWebhook={props.onUpdateWebhook}
            onDeleteWebhook={props.onDeleteWebhook}
            embedded
          />
        )}

        {subPage === 'plugins' && (
          <PluginsPanel
            open={true}
            onClose={() => setSubPage('chat')}
            embedded
          />
        )}

        {subPage === 'printer' && (
          <PrinterPage />
        )}
      </div>
    </div>
  )
}
