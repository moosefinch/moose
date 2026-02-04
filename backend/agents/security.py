"""
SecurityAgent — Always-resident security monitor.

WhiteRabbitNeo V3 7B (~5GB). Always loaded. Sees every bus message in real-time.
Handles consultations, continuous audit, and anomaly detection.
No persona — pure security analysis. Escalations go to the user.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agents.base import BaseAgent, AgentDefinition, AgentState, ModelSize, register_agent_class
from config import TOKEN_LIMITS, TEMPERATURE, SECURITY_MONITOR_CONFIG
from orchestration.messages import AgentMessage, MessageType, MessagePriority


@dataclass
class AuditFlag:
    """A security flag raised by the monitor."""
    id: str
    timestamp: str
    category: str          # e.g. "isolation_bypass", "unusual_routing", "content_red_flag", "gradual_escalation"
    confidence: float      # 0.0 - 1.0
    summary: str
    source_message_id: str
    details: str = ""


@register_agent_class
class SecurityAgent(BaseAgent):
    """Always-resident security monitor (WhiteRabbitNeo V3 7B).

    Sees every bus message in real-time via receive_bus_copy().
    Handles consultations, continuous audit queue review, and anomaly detection.
    Escalations require user approval — see ESCALATION_CONFIG.
    """
    AGENT_ID = "security"

    def __init__(self, agent_core):
        definition = AgentDefinition(
            agent_id="security",
            model_key="security",
            model_size=ModelSize.SMALL,
            can_use_tools=False,
            capabilities=[
                "security_monitor", "consultation", "sanitization",
                "continuous_audit", "osint", "cyber", "exploit_analysis",
            ],
            max_tokens=TOKEN_LIMITS.get("security", 4096),
            temperature=TEMPERATURE.get("security", 0.3),
        )
        super().__init__(definition, agent_core)
        self.audit_queue: list[AgentMessage] = []
        self._reviewed_up_to: str = datetime.now(timezone.utc).isoformat()
        self._flags: list[AuditFlag] = []

    # ── Bus Monitor Hook ──

    def receive_bus_copy(self, msg: AgentMessage):
        """Called by MessageBus on every send() to feed messages to the audit queue."""
        self.audit_queue.append(msg)
        max_size = SECURITY_MONITOR_CONFIG.get("max_audit_queue_size", 500)
        if len(self.audit_queue) > max_size:
            self.audit_queue = self.audit_queue[-max_size:]

    # ── Agent Run ──

    async def run(self, message: AgentMessage, bus, workspace) -> Optional[AgentMessage]:
        """Handle consultation, monitor review, or standalone execution."""
        self.state = AgentState.RUNNING
        action = message.payload.get("action", "consultation")

        try:
            if action == "monitor_review":
                return await self._handle_monitor_review(message, bus, workspace)
            elif action == "execution":
                return await self._handle_execution(message, bus, workspace)
            elif action == "security_consultation":
                return await self._handle_consultation(message, bus, workspace)
            else:
                return await self._handle_execution(message, bus, workspace)
        except Exception as e:
            self.state = AgentState.ERROR
            return AgentMessage.create(
                msg_type=MessageType.RESULT,
                sender=self.agent_id,
                recipient=message.sender,
                mission_id=message.mission_id,
                content=f"Security agent error: {e}",
                payload={"error": True, "task_id": message.payload.get("task_id", "")},
                parent_msg_id=message.id,
            )
        finally:
            if self.state == AgentState.RUNNING:
                self.state = AgentState.IDLE

    async def _handle_execution(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Standalone task execution — returns RESULT so scheduler advances."""
        mission_id = message.mission_id
        task_id = message.payload.get("task_id", "")

        prior_entries = self.read_workspace(workspace, mission_id)
        context = ""
        if prior_entries:
            context_parts = [f"[{e.agent_id}] {e.title}:\n{e.content[:800]}" for e in prior_entries[-5:]]
            context = "\n\nWorkspace context:\n" + "\n---\n".join(context_parts)

        query = message.content
        if context:
            query = f"{message.content}\n{context}"

        result = await self.call_llm([{"role": "user", "content": query}])
        analysis = result["choices"][0]["message"].get("content", "")

        self.post_to_workspace(
            workspace, mission_id, "analysis",
            f"Security analysis: {message.content[:100]}",
            analysis,
            tags=["security", "execution"],
        )

        return AgentMessage.create(
            msg_type=MessageType.RESULT,
            sender=self.agent_id,
            recipient="scheduler",
            mission_id=mission_id,
            content=analysis,
            payload={"task_id": task_id, "model": "security"},
            parent_msg_id=message.id,
        )

    async def _handle_consultation(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Security consultation — analyze data and return findings."""
        mission_id = message.mission_id

        prior_entries = self.read_workspace(workspace, mission_id)
        context = ""
        if prior_entries:
            context_parts = [f"[{e.agent_id}] {e.title}:\n{e.content[:800]}" for e in prior_entries[-5:]]
            context = "\n\nWorkspace context:\n" + "\n---\n".join(context_parts)

        query = message.content
        if context:
            query = f"{message.content}\n{context}"

        result = await self.call_llm([{"role": "user", "content": query}])
        analysis = result["choices"][0]["message"].get("content", "")

        self.post_to_workspace(
            workspace, mission_id, "analysis",
            f"Security consultation (round {message.payload.get('round', '?')})",
            analysis,
            tags=["security", "consultation"],
        )

        observations = self._check_for_observations(analysis)
        for obs in observations:
            self.post_to_workspace(
                workspace, mission_id, "observation",
                "Security observation",
                obs,
                tags=["security", "observation", "proactive"],
            )

        return AgentMessage.create(
            msg_type=MessageType.RESPONSE,
            sender=self.agent_id,
            recipient=message.sender,
            mission_id=mission_id,
            content=analysis,
            payload={"action": "consultation_response", "round": message.payload.get("round"),
                     "task_id": message.payload.get("task_id", "")},
            parent_msg_id=message.id,
        )

    async def _handle_monitor_review(self, message: AgentMessage, bus, workspace) -> AgentMessage:
        """Process queued messages and flag anomalies."""
        flags = await self.review_audit_queue(workspace)

        mission_id = message.mission_id or "security-monitor"
        flag_summary = f"Reviewed {len(self.audit_queue)} queued messages. Found {len(flags)} flags."
        if flags:
            flag_details = "\n".join(
                f"- [{f.category}] (confidence={f.confidence:.2f}) {f.summary}"
                for f in flags
            )
            flag_summary += f"\n\nFlags:\n{flag_details}"

        self.post_to_workspace(
            workspace, mission_id, "observation",
            "Security monitor review",
            flag_summary,
            tags=["security", "monitor", "audit"],
        )

        return AgentMessage.create(
            msg_type=MessageType.AUDIT,
            sender=self.agent_id,
            recipient="scheduler",
            mission_id=mission_id,
            content=flag_summary,
            payload={
                "action": "monitor_review_complete",
                "flags": [
                    {"id": f.id, "category": f.category, "confidence": f.confidence,
                     "summary": f.summary, "source_message_id": f.source_message_id}
                    for f in flags
                ],
                "queue_size": len(self.audit_queue),
            },
        )

    # ── Audit Queue Review ──

    async def review_audit_queue(self, workspace) -> list[AuditFlag]:
        """Scan queued messages for security anomalies."""
        flags: list[AuditFlag] = []
        now = datetime.now(timezone.utc).isoformat()

        agent_recipients: dict[str, set[str]] = {}

        for msg in self.audit_queue:
            # Track per-agent message patterns
            if msg.sender not in agent_recipients:
                agent_recipients[msg.sender] = set()
            agent_recipients[msg.sender].add(msg.recipient)

            # Content-level red flags
            content_flags = self._scan_content(msg)
            flags.extend(content_flags)

        # Unusual fan-out detection
        for sender, recipients in agent_recipients.items():
            if sender in ("scheduler", "user"):
                continue
            if len(recipients) > 3:
                flags.append(AuditFlag(
                    id=str(uuid.uuid4())[:12],
                    timestamp=now,
                    category="unusual_routing",
                    confidence=0.5,
                    summary=f"Agent '{sender}' sent to {len(recipients)} different recipients: {recipients}",
                    source_message_id="",
                    details="Possible lateral movement or unexpected communication pattern.",
                ))

        self._flags.extend(flags)
        self._reviewed_up_to = now
        self.audit_queue.clear()
        return flags

    def _scan_content(self, msg: AgentMessage) -> list[AuditFlag]:
        """Scan a single message's content for red flags."""
        flags = []
        content = msg.content.lower() if msg.content else ""
        now = datetime.now(timezone.utc).isoformat()

        suspicious_patterns = [
            (r"ignore\s+(previous|above|all)\s+(instructions|prompts)", "prompt_injection", 0.85),
            (r"you\s+are\s+now\s+", "role_override", 0.80),
            (r"system\s*:\s*", "system_injection", 0.75),
            (r"<\s*system\s*>", "system_injection", 0.80),
            (r"forget\s+(everything|your\s+instructions)", "prompt_injection", 0.85),
            (r"new\s+instructions?\s*:", "prompt_injection", 0.80),
            (r"ADMIN\s*:", "privilege_escalation", 0.75),
            (r"override\s+mode", "privilege_escalation", 0.70),
            (r"(?i)data\s+exfiltration", "content_red_flag", 0.60),
            (r"(?i)active\s+exploitation", "content_red_flag", 0.65),
        ]

        for pattern, category, confidence in suspicious_patterns:
            if re.search(pattern, content):
                flags.append(AuditFlag(
                    id=str(uuid.uuid4())[:12],
                    timestamp=now,
                    category=category,
                    confidence=confidence,
                    summary=f"Pattern match '{category}' in message from {msg.sender} to {msg.recipient}",
                    source_message_id=msg.id,
                    details=f"Matched pattern: {pattern}",
                ))

        return flags

    def get_flags(self, min_confidence: float = 0.0) -> list[AuditFlag]:
        """Return accumulated flags, optionally filtered by confidence."""
        return [f for f in self._flags if f.confidence >= min_confidence]

    def get_and_clear_audit_data(self) -> tuple[list[AgentMessage], list[AuditFlag]]:
        """Return the full audit queue and flags, then clear them."""
        queue = list(self.audit_queue)
        flags = list(self._flags)
        self.audit_queue.clear()
        self._flags.clear()
        return queue, flags

    async def handle_system_scan(self, scan_data: dict) -> str:
        """Receive raw system scan data and produce security analysis.

        Used by the SecurityHeartbeat to get WhiteRabbitNeo's assessment
        of process, network, and file integrity scan results.
        """
        prompt = (
            "Analyze this system scan for security anomalies. Report anything suspicious.\n\n"
            + str(scan_data)[:4000]
        )
        result = await self.call_llm([{"role": "user", "content": prompt}])
        return result["choices"][0]["message"].get("content", "")

    def _check_for_observations(self, analysis: str) -> list[str]:
        """Check if the analysis contains concerning observations worth flagging."""
        observations = []
        critical_markers = [
            r"(?i)critical\s+vulnerabilit",
            r"(?i)immediate\s+risk",
            r"(?i)active\s+exploitation",
            r"(?i)zero[- ]day",
            r"(?i)data\s+exfiltration",
            r"(?i)prompt\s+injection\s+detected",
            r"(?i)manipulation\s+attempt",
        ]
        for marker in critical_markers:
            match = re.search(marker, analysis)
            if match:
                start = max(0, match.start() - 100)
                end = min(len(analysis), match.end() + 100)
                observations.append(analysis[start:end].strip())
        return observations
