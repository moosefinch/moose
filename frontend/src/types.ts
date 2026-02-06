export interface ChatMessage {
  role: 'user' | 'assistant' | 'notification' | 'proactive'
  content: string
  model_key?: string
  model_label?: string
  elapsed_seconds?: number
  tool_calls?: ToolCall[]
  plan?: PlanData | null
  error?: boolean
  _streaming?: boolean
  audio_url?: string
  audio_id?: string
  voice_mode?: boolean
  proactive_category?: string
}

export interface ToolCall {
  tool: string
  args?: Record<string, unknown>
  result?: string
}

export interface PlanData {
  tasks: PlanTask[]
  complexity?: string
  summary?: string
  synthesized?: boolean
}

export interface PlanTask {
  model: string
  task: string
  depends_on?: string[]
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count?: number
  first_message?: string
}

export interface AgentTask {
  id: string
  description: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  plan?: unknown
  progress_log?: { message: string }[]
  result?: string
  created_at: string
  updated_at?: string
}

export interface Briefing {
  id: string
  task_id?: string
  content: string
  created_at: string
  read: boolean
}

export interface AgentState {
  id?: string
  name: string
  model_key?: string
  model_size?: string
  state: 'idle' | 'running' | 'waiting' | 'error' | 'completed'
  capabilities?: string[]
}

export interface AgentEvent {
  id: string
  time: string
  eventType: string
  agent: string
  detail: string
  from_model?: string
  to_model?: string
  tool?: string
  args_preview?: string
  task_preview?: string
  target?: string
  msgType?: string
}

export interface Mission {
  mission_id?: string
  status?: string
  completed: number
  total: number
  active_agent?: string
}

export interface OverlayData {
  id: string
  overlay_type: string
  geojson: unknown
  style?: Record<string, unknown>
  label?: string
  visible?: boolean
}

export interface ModelStatus {
  id: string
  label?: string
  state?: 'loaded' | 'downloaded' | 'not_loaded'
}

export type SystemState = 'idle' | 'listening' | 'thinking' | 'working' | 'consulting' | 'presenting' | 'alert'

export type ViewportMode = 'avatar' | 'map' | '3d' | 'image' | 'document' | 'data'

export interface ViewportCommand {
  command: 'load_3d' | 'show_image' | 'show_map' | 'show_data' | 'clear'
  url?: string
  metadata?: string
}

export interface ChannelMessage {
  id: string
  channel: string
  sender: string
  content: string
  timestamp: string
  payload?: Record<string, unknown>
}

export type ContextPanelSection = 'viewport' | 'agents' | 'tasks' | 'briefings' | 'events'

export interface ChannelPostRequest {
  channel: string
  content: string
  sender?: string
}

export interface MemorySearchResult {
  text: string
  score: number
  timestamp?: string
  tags?: string
}

export interface ContextCard {
  id: string
  type: 'viewport' | 'mission' | 'notification' | 'completion' | 'finding' | 'proactive'
  title: string
  content: unknown
  timestamp: string
  stale?: boolean
  color: 'cyan' | 'green' | 'amber' | 'red' | 'purple'
  confidence?: number
  sources?: string[]
}

export interface PendingEmail {
  id: string
  persona_id?: string
  prospect_id?: string
  contact_id?: string
  campaign_id?: string
  subject?: string
  body?: string
  status: string
  contact_name?: string
  contact_email?: string
  prospect_company?: string
  created_at: number
  updated_at: number
}

export interface ContentDraft {
  id: string
  content_type: string
  title: string
  body?: string
  platform?: string
  campaign_id?: string
  status: string
  tags?: string
  created_at: number
  updated_at: number
}

export interface MarketingStats {
  emails: Record<string, number>
  content: Record<string, number>
  personas: number
  prospects: number
  cadences: { loop_type: string; enabled: number; last_run?: number; next_run?: number }[]
}

export interface MarketingCadence {
  id: string
  loop_type: string
  interval_seconds: number
  enabled: number
  last_run?: number
  next_run?: number
  config?: string
  created_at: number
  updated_at: number
}

export interface ICPPersona {
  id: string
  name: string
  archetype: string
  description?: string
  industry?: string
  firm_size?: string
  pain_points?: string
  talking_points?: string
  compliance_frameworks?: string
  email_tone?: string
  preferred_platforms?: string
  created_at: number
  updated_at: number
}

export interface CognitiveStatus {
  phase: 'idle' | 'observe' | 'orient' | 'advocate' | 'decide' | 'act'
  cycle: number
  observations: number
  thoughts: number
}

export interface VoiceStatus {
  tts: boolean
  stt: boolean
}

export interface ScheduledJob {
  id: string
  description: string
  schedule_type: 'interval' | 'cron' | 'once'
  schedule_value: string
  agent_id?: string
  task_payload?: string
  enabled: number
  last_run?: string
  next_run?: string
  created_at: string
  run_count: number
}

export interface WebhookEndpoint {
  id: string
  name: string
  slug: string
  source_type: string
  secret?: string
  action_type: string
  action_payload?: string
  enabled: number
  created_at: string
}

export interface AdvocacyGoal {
  id: string
  text: string
  category: string
  priority: number
  parent_id?: string
  tensions: string[]
  status: string
  evidence: { type: string; description: string; last_observed: string }[]
  created_at: string
  updated_at: string
  inferred: boolean
  confirmed: boolean
}

export interface AdvocacyPattern {
  id: string
  type: string
  description: string
  evidence: string[]
  first_observed: string
  last_observed: string
  occurrences: number
  friction_level: number
  dismissed: boolean
  escalated: boolean
  related_goals: string[]
}

export interface ImprovementProposal {
  id: string
  created_at: number
  status: 'pending' | 'approved' | 'executing' | 'completed' | 'failed' | 'rejected'
  category: string
  severity: string
  gap_description: string
  gap_evidence: Record<string, unknown>
  solution_type: string
  solution_summary: string
  solution_details: Record<string, unknown>
  reasoning: string
  execution_log: { timestamp: number; message: string }[]
  approved_at?: number
  executed_at?: number
  completed_at?: number
  result?: string
  error?: string
}

export interface AdvocacyStatus {
  enabled: boolean
  profile: string
  active_goals: number
  unconfirmed_goals: number
  active_patterns: number
  friction?: { flags_today: number; max_flags_per_day: number; queued: number }
  developmental?: { mode: string }
  onboarding?: { stage: string; started: boolean; complete: boolean }
}
