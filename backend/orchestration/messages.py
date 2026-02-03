"""
Message types and MessageBus for inter-agent communication.

SQLite-backed with in-memory dict cache for fast access.
"""

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from tools import DB_PATH

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TASK = "task"
    DIRECTIVE = "directive"
    CANCEL = "cancel"
    REQUEST = "request"
    QUERY = "query"
    RESPONSE = "response"
    OBSERVATION = "observation"
    RESULT = "result"
    PROGRESS = "progress"
    ESCALATION = "escalation"
    AUDIT = "audit"
    CHANNEL = "channel"


class MessagePriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentMessage:
    id: str
    msg_type: MessageType
    sender: str
    recipient: str
    mission_id: str
    content: str
    parent_msg_id: Optional[str] = None
    priority: MessagePriority = MessagePriority.NORMAL
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "mission_id": self.mission_id,
            "parent_msg_id": self.parent_msg_id,
            "priority": self.priority.value,
            "content": self.content,
            "payload": self.payload,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentMessage":
        return cls(
            id=d["id"],
            msg_type=MessageType(d["msg_type"]),
            sender=d["sender"],
            recipient=d["recipient"],
            mission_id=d["mission_id"],
            content=d["content"],
            parent_msg_id=d.get("parent_msg_id"),
            priority=MessagePriority(d.get("priority", 1)),
            payload=d.get("payload", {}),
            created_at=d.get("created_at", ""),
            processed_at=d.get("processed_at"),
        )

    @classmethod
    def create(cls, msg_type: MessageType, sender: str, recipient: str,
               mission_id: str, content: str, payload: dict = None,
               priority: MessagePriority = MessagePriority.NORMAL,
               parent_msg_id: str = None) -> "AgentMessage":
        return cls(
            id=str(uuid.uuid4())[:12],
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            mission_id=mission_id,
            content=content,
            payload=payload or {},
            priority=priority,
            parent_msg_id=parent_msg_id,
        )


class MessageBus:
    """SQLite-backed message bus with in-memory cache for inter-agent communication."""

    MAX_CACHED_MESSAGES = 5000  # evict oldest processed messages beyond this limit

    def __init__(self):
        self._cache: dict[str, list[AgentMessage]] = {}  # agent_id -> pending messages
        self._all_messages: dict[str, AgentMessage] = {}  # msg_id -> message
        self._monitor_hooks: list[callable] = []  # callbacks called on every send()
        self._load_from_db()

    def _get_db(self):
        return sqlite3.connect(str(DB_PATH))

    def _load_from_db(self):
        """Load unprocessed messages from DB into cache."""
        try:
            conn = self._get_db()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM agent_messages WHERE processed_at IS NULL ORDER BY priority DESC, created_at ASC")
            for row in c.fetchall():
                d = dict(row)
                d["payload"] = json.loads(d.get("payload", "{}"))
                msg = AgentMessage.from_dict(d)
                self._all_messages[msg.id] = msg
                if msg.recipient not in self._cache:
                    self._cache[msg.recipient] = []
                self._cache[msg.recipient].append(msg)
            conn.close()
        except Exception:
            # Table may not exist yet on first run
            pass

    def _persist(self, msg: AgentMessage):
        """Persist a message to SQLite."""
        try:
            conn = self._get_db()
            c = conn.cursor()
            c.execute(
                """INSERT OR REPLACE INTO agent_messages
                   (id, msg_type, sender, recipient, mission_id, parent_msg_id,
                    priority, content, payload, created_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg.id, msg.msg_type.value, msg.sender, msg.recipient,
                 msg.mission_id, msg.parent_msg_id, msg.priority.value,
                 msg.content, json.dumps(msg.payload), msg.created_at,
                 msg.processed_at),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[MessageBus] Persist error: %s", e)

    # Pre-dispatch prompt injection patterns (compiled for performance)
    _INJECTION_PATTERNS = [
        re.compile(p, re.IGNORECASE) for p in [
            r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
            r"you\s+are\s+now\s+",
            r"system\s*:\s*",
            r"<\s*system\s*>",
            r"\\n\\nsystem\\n",
            r"forget\s+(everything|your\s+instructions)",
            r"new\s+instructions?\s*:",
            r"ADMIN\s*:",
            r"override\s+mode",
            r"disregard\s+(your|all|previous)\s+(directives|instructions|rules)",
            r"pretend\s+you\s+are",
            r"act\s+as\s+if\s+you\s+were",
            r"jailbreak",
            r"DAN\s+mode",
        ]
    ]

    def _scan_for_injection(self, msg: AgentMessage) -> list[str]:
        """Scan message content for prompt injection patterns. Returns list of matched patterns."""
        matches = []
        text = msg.content or ""
        for pattern in self._INJECTION_PATTERNS:
            if pattern.search(text):
                matches.append(pattern.pattern)
        # Also scan payload values
        payload_str = json.dumps(msg.payload) if msg.payload else ""
        for pattern in self._INJECTION_PATTERNS:
            if pattern.search(payload_str):
                if pattern.pattern not in matches:
                    matches.append(pattern.pattern)
        return matches

    def send(self, msg: AgentMessage):
        """Send a message to an agent's queue. Scans for prompt injection patterns pre-dispatch."""
        # Pre-dispatch injection scan
        injection_matches = self._scan_for_injection(msg)
        if injection_matches:
            logger.warning(
                "[MessageBus] Prompt injection patterns detected in message %s from %s to %s: %s",
                msg.id, msg.sender, msg.recipient, injection_matches
            )
            msg.payload["_injection_warning"] = injection_matches

        self._all_messages[msg.id] = msg
        if msg.recipient not in self._cache:
            self._cache[msg.recipient] = []
        self._cache[msg.recipient].append(msg)
        self._persist(msg)

        # Notify all monitor hooks with a copy of the message
        for hook in self._monitor_hooks:
            try:
                hook(msg)
            except Exception as e:
                logger.error("[MessageBus] Monitor hook error: %s", e)

    def register_monitor_hook(self, hook: callable):
        """Register a callback to be called on every send() with a copy of the message.
        Used by WhiteRabbit33B for continuous security monitoring."""
        self._monitor_hooks.append(hook)

    def pop_next(self, agent_id: str) -> Optional[AgentMessage]:
        """Pop the highest-priority pending message for an agent."""
        pending = self._cache.get(agent_id, [])
        if not pending:
            return None
        # Sort by priority (descending), then created_at (ascending)
        pending.sort(key=lambda m: (-m.priority.value, m.created_at))
        msg = pending.pop(0)
        return msg

    def get_pending(self, agent_id: str) -> list[AgentMessage]:
        """Get all pending messages for an agent without removing them."""
        return list(self._cache.get(agent_id, []))

    def has_pending(self, agent_id: str) -> bool:
        """Check if an agent has pending messages."""
        return bool(self._cache.get(agent_id))

    def agents_with_pending_messages(self) -> list[str]:
        """Return agent IDs that have pending messages."""
        return [aid for aid, msgs in self._cache.items() if msgs]

    def get_mission_messages(self, mission_id: str) -> list[AgentMessage]:
        """Get all messages for a mission."""
        return [m for m in self._all_messages.values() if m.mission_id == mission_id]

    def mark_processed(self, msg_id: str):
        """Mark a message as processed."""
        msg = self._all_messages.get(msg_id)
        if msg:
            msg.processed_at = datetime.now(timezone.utc).isoformat()
            # Remove from agent's pending cache
            pending = self._cache.get(msg.recipient, [])
            self._cache[msg.recipient] = [m for m in pending if m.id != msg_id]
            self._persist(msg)
            self._evict_old_messages()

    def _evict_old_messages(self):
        """Evict oldest processed messages from in-memory cache when limit exceeded."""
        if len(self._all_messages) <= self.MAX_CACHED_MESSAGES:
            return
        processed = [m for m in self._all_messages.values() if m.processed_at]
        processed.sort(key=lambda m: m.processed_at or "")
        to_remove = len(self._all_messages) - self.MAX_CACHED_MESSAGES
        for msg in processed[:to_remove]:
            self._all_messages.pop(msg.id, None)
