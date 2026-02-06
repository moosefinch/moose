"""
Pydantic request/response models shared across route modules.
"""

from typing import Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatQuery(BaseModel):
    query: str
    context: Optional[str] = None
    history: Optional[list[ChatMessage]] = None
    use_tools: bool = True
    conversation_id: Optional[str] = None
    stream: bool = False


class ConversationUpdate(BaseModel):
    title: str


class OverlayRequest(BaseModel):
    overlay_type: str
    geojson: dict
    style: Optional[dict] = {}
    label: Optional[str] = ""


class TaskRequest(BaseModel):
    description: str
    plan: Optional[list[dict]] = None


class ChannelPostRequest(BaseModel):
    channel: str
    content: str
    sender: Optional[str] = "operator"


class MarketingEmailUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class PersonaCreate(BaseModel):
    name: str
    archetype: str
    description: Optional[str] = ""
    industry: Optional[str] = ""
    firm_size: Optional[str] = ""
    pain_points: Optional[str] = ""
    talking_points: Optional[str] = ""
    compliance_frameworks: Optional[str] = ""
    email_tone: Optional[str] = ""
    preferred_platforms: Optional[str] = ""


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    firm_size: Optional[str] = None
    pain_points: Optional[str] = None
    talking_points: Optional[str] = None
    compliance_frameworks: Optional[str] = None
    email_tone: Optional[str] = None
    preferred_platforms: Optional[str] = None


class CadenceUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = None


class SmtpTestRequest(BaseModel):
    to_email: str


class ApprovalRequest(BaseModel):
    approved: bool


class ContentDraftUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[str] = None


class ScheduledJobCreate(BaseModel):
    description: str
    schedule_type: str  # 'interval', 'cron', 'once'
    schedule_value: str  # seconds for interval, cron expr, ISO for once
    agent_id: Optional[str] = ""
    task_payload: Optional[str] = ""


class ScheduledJobUpdate(BaseModel):
    description: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_value: Optional[str] = None
    enabled: Optional[bool] = None
    agent_id: Optional[str] = None
    task_payload: Optional[str] = None


class NaturalScheduleRequest(BaseModel):
    text: str


class WebhookCreate(BaseModel):
    name: str
    slug: str
    source_type: str = "generic"  # 'generic', 'github'
    secret: Optional[str] = None
    action_type: str = "start_task"  # 'start_task', 'chat', 'notify'
    action_payload: Optional[str] = ""


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    secret: Optional[str] = None
    action_type: Optional[str] = None
    action_payload: Optional[str] = None
    enabled: Optional[bool] = None


class GoalCreate(BaseModel):
    text: str
    category: str = "other"
    priority: float = 0.5
    parent_id: Optional[str] = None


class GoalUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[float] = None


class EvidenceCreate(BaseModel):
    type: str = "stated"
    description: str


class OnboardingResponse(BaseModel):
    text: str


class ProposalDecision(BaseModel):
    approved: bool
    notes: str = ""
