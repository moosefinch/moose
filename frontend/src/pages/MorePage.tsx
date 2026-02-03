import { useNavigation, type MoreSubPage } from '../contexts/NavigationContext'
import { Sidebar } from '../components/Sidebar'
import { ChatPanel } from '../components/ChatPanel'
import { ChannelsDrawer } from '../components/ChannelsDrawer'
import { MemoryExplorer } from '../components/MemoryExplorer'
import { MarketingDrawer } from '../components/MarketingDrawer'
import { SchedulingDrawer } from '../components/SchedulingDrawer'
import { PluginsPanel } from '../components/PluginsPanel'
import type { ChatMessage, AgentState, ChannelMessage, PendingEmail, ContentDraft, MarketingStats, ScheduledJob, WebhookEndpoint } from '../types'

const SUB_TABS: { id: MoreSubPage; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'channels', label: 'Channels' },
  { id: 'memory', label: 'Memory' },
  { id: 'marketing', label: 'Marketing' },
  { id: 'scheduling', label: 'Scheduling' },
  { id: 'plugins', label: 'Plugins' },
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
  // Sidebar / Conversations
  conversations: { id: string; title: string; created_at: string; updated_at: string }[]
  activeConvoId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onDeleteConversation: (id: string) => void
  agents: AgentState[]
  connected: boolean
  apiUp: boolean
  // Channels
  channelMessages: ChannelMessage[]
  onPostMessage: (channel: string, content: string) => Promise<boolean>
  // Memory
  memoryCount: number
  onSearchMemory: (q: string, topK?: number) => Promise<{ text: string; score: number }[]>
  // Marketing
  crmEnabled: boolean
  pendingEmails: PendingEmail[]
  pendingContent: ContentDraft[]
  marketingStats: MarketingStats | null
  onApproveEmail: (id: string) => void
  onRejectEmail: (id: string) => void
  onApproveContent: (id: string) => void
  onRejectContent: (id: string) => void
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
}

export function MorePage(props: MorePageProps) {
  const { subPage, setSubPage } = useNavigation()

  return (
    <div className="page-more">
      <div className="more-sub-tabs">
        {SUB_TABS.filter(t => t.id !== 'marketing' || props.crmEnabled).map(tab => (
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
              conversations={props.conversations}
              activeConvoId={props.activeConvoId}
              onSelectConversation={props.onSelectConversation}
              onNewConversation={props.onNewConversation}
              onDeleteConversation={props.onDeleteConversation}
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
      </div>
    </div>
  )
}
