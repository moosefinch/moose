"""
ChannelManager — Named communication channels with agent permissions.

Each channel has a set of allowed agents. Agents can only post/read
channels they have permission for. Backed by SQLite.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from tools import DB_PATH
from config import CHANNEL_DEFINITIONS

logger = logging.getLogger(__name__)


@dataclass
class ChannelMessage:
    id: str
    channel: str
    sender: str
    content: str
    timestamp: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelMessage":
        return cls(
            id=d["id"],
            channel=d["channel"],
            sender=d["sender"],
            content=d["content"],
            timestamp=d["timestamp"],
            payload=d.get("payload", {}),
        )


@dataclass
class Channel:
    name: str
    allowed_agents: set[str]
    messages: list[ChannelMessage] = field(default_factory=list)


class ChannelManager:
    """Manages named communication channels with agent-level permissions."""

    def __init__(self, agent_core=None):
        self._core = agent_core
        self._channels: dict[str, Channel] = {}
        self._init_db()
        self._init_channels()
        self._load_from_db()

    def _get_db(self):
        return sqlite3.connect(str(DB_PATH))

    def _init_db(self):
        """Create channel_messages table if it doesn't exist."""
        try:
            conn = self._get_db()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS channel_messages (
                id TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT DEFAULT '{}'
            )''')
            c.execute('CREATE INDEX IF NOT EXISTS idx_channel_messages_channel ON channel_messages(channel)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_channel_messages_timestamp ON channel_messages(timestamp)')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("DB init error: %s", e)

    def _init_channels(self):
        """Initialize channels from config definitions."""
        for name, allowed in CHANNEL_DEFINITIONS.items():
            self._channels[name] = Channel(
                name=name,
                allowed_agents=set(allowed),
            )

    def _load_from_db(self):
        """Load recent messages from DB into channel caches."""
        try:
            conn = self._get_db()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""SELECT * FROM channel_messages
                        ORDER BY timestamp DESC LIMIT 500""")
            rows = c.fetchall()
            conn.close()

            for row in reversed(rows):
                d = dict(row)
                d["payload"] = json.loads(d.get("payload", "{}"))
                msg = ChannelMessage.from_dict(d)
                channel = self._channels.get(msg.channel)
                if channel:
                    channel.messages.append(msg)
        except Exception:
            pass

    def _persist(self, msg: ChannelMessage):
        """Persist a channel message to SQLite."""
        try:
            conn = self._get_db()
            c = conn.cursor()
            c.execute(
                """INSERT INTO channel_messages (id, channel, sender, content, timestamp, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (msg.id, msg.channel, msg.sender, msg.content,
                 msg.timestamp, json.dumps(msg.payload)),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Persist error: %s", e)

    def post(self, channel_name: str, sender: str, content: str,
             payload: dict = None) -> Optional[ChannelMessage]:
        """Post a message to a channel. Enforces sender permission."""
        channel = self._channels.get(channel_name)
        if not channel:
            logger.warning("Unknown channel: %s", channel_name)
            return None

        if sender not in channel.allowed_agents:
            logger.warning("BLOCKED: %s not allowed in %s", sender, channel_name)
            return None

        msg = ChannelMessage(
            id=str(uuid.uuid4())[:12],
            channel=channel_name,
            sender=sender,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=payload or {},
        )

        channel.messages.append(msg)
        # Keep channel buffer bounded
        if len(channel.messages) > 200:
            channel.messages = channel.messages[-200:]

        self._persist(msg)
        return msg

    def read(self, channel_name: str, agent_id: str,
             since: Optional[str] = None, limit: int = 50) -> list[ChannelMessage]:
        """Read messages from a channel. Returns empty if agent lacks permission."""
        channel = self._channels.get(channel_name)
        if not channel:
            return []

        if agent_id not in channel.allowed_agents:
            return []

        messages = channel.messages
        if since:
            messages = [m for m in messages if m.timestamp > since]

        return messages[-limit:]

    def get_channels_for(self, agent_id: str) -> list[str]:
        """Return list of channel names an agent can see."""
        return [
            name for name, ch in self._channels.items()
            if agent_id in ch.allowed_agents
        ]

    def get_all_channels(self) -> list[dict]:
        """Return all channels with message counts (for API)."""
        result = []
        for name, ch in self._channels.items():
            result.append({
                "name": name,
                "allowed_agents": sorted(ch.allowed_agents),
                "message_count": len(ch.messages),
                "last_message": ch.messages[-1].to_dict() if ch.messages else None,
            })
        return result

    def get_channel_messages(self, channel_name: str,
                             limit: int = 50) -> list[dict]:
        """Get messages for a channel (for API — no permission check, owner's frontend)."""
        channel = self._channels.get(channel_name)
        if not channel:
            return []
        return [m.to_dict() for m in channel.messages[-limit:]]
