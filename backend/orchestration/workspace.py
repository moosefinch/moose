"""
SharedWorkspace — structured data exchange between agents within a mission.

SQLite-backed with in-memory cache by mission_id.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from tools import DB_PATH

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceEntry:
    id: str
    mission_id: str
    agent_id: str
    entry_type: str  # finding, analysis, recommendation, observation, raw_intel, tool_output
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_id": self.mission_id,
            "agent_id": self.agent_id,
            "entry_type": self.entry_type,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "references": self.references,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkspaceEntry":
        return cls(
            id=d["id"],
            mission_id=d["mission_id"],
            agent_id=d["agent_id"],
            entry_type=d["entry_type"],
            title=d["title"],
            content=d["content"],
            tags=d.get("tags", []),
            references=d.get("references", []),
            created_at=d.get("created_at", ""),
        )


class SharedWorkspace:
    """Mission-scoped workspace for agents to share findings."""

    MAX_CACHED_MISSIONS = 100  # evict oldest missions beyond this limit

    def __init__(self):
        self._cache: dict[str, list[WorkspaceEntry]] = {}  # mission_id -> entries
        self._load_from_db()

    def _get_db(self):
        return sqlite3.connect(str(DB_PATH))

    def _load_from_db(self):
        """Load workspace entries from DB into cache."""
        try:
            conn = self._get_db()
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM workspace_entries ORDER BY created_at ASC")
            for row in c.fetchall():
                d = dict(row)
                d["tags"] = json.loads(d.get("tags", "[]"))
                d["references"] = json.loads(d.pop("reference_list", "[]"))
                entry = WorkspaceEntry.from_dict(d)
                if entry.mission_id not in self._cache:
                    self._cache[entry.mission_id] = []
                self._cache[entry.mission_id].append(entry)
            conn.close()
        except Exception:
            pass

    def _persist(self, entry: WorkspaceEntry):
        """Persist an entry to SQLite."""
        try:
            conn = self._get_db()
            c = conn.cursor()
            c.execute(
                """INSERT OR REPLACE INTO workspace_entries
                   (id, mission_id, agent_id, entry_type, title, content,
                    tags, reference_list, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.mission_id, entry.agent_id, entry.entry_type,
                 entry.title, entry.content, json.dumps(entry.tags),
                 json.dumps(entry.references), entry.created_at),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Persist error: %s", e)

    def add(self, entry: WorkspaceEntry):
        """Add an entry to the workspace."""
        if entry.mission_id not in self._cache:
            self._cache[entry.mission_id] = []
        self._cache[entry.mission_id].append(entry)
        self._persist(entry)
        self._evict_old_missions()

    def _evict_old_missions(self):
        """Evict oldest missions from in-memory cache when limit exceeded."""
        if len(self._cache) <= self.MAX_CACHED_MISSIONS:
            return
        # Sort missions by earliest entry created_at, evict oldest
        mission_ages = []
        for mid, entries in self._cache.items():
            earliest = min((e.created_at for e in entries), default="")
            mission_ages.append((mid, earliest))
        mission_ages.sort(key=lambda x: x[1])
        to_remove = len(self._cache) - self.MAX_CACHED_MISSIONS
        for mid, _ in mission_ages[:to_remove]:
            del self._cache[mid]

    def query(self, mission_id: str, agent_id: str = None,
              entry_type: str = None) -> list[WorkspaceEntry]:
        """Query workspace entries with optional filters."""
        entries = self._cache.get(mission_id, [])
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if entry_type:
            entries = [e for e in entries if e.entry_type == entry_type]
        return entries

    def get_mission_summary(self, mission_id: str) -> str:
        """Build a text summary of all workspace entries for a mission."""
        entries = self._cache.get(mission_id, [])
        if not entries:
            return "No workspace entries for this mission."
        parts = []
        for e in entries:
            tags_str = f" [{', '.join(e.tags)}]" if e.tags else ""
            parts.append(f"### [{e.agent_id}] {e.title}{tags_str}\n{e.content}")
        return "\n\n---\n\n".join(parts)

    def clear_mission(self, mission_id: str):
        """Clear all entries for a mission."""
        self._cache.pop(mission_id, None)
        try:
            conn = self._get_db()
            c = conn.cursor()
            c.execute("DELETE FROM workspace_entries WHERE mission_id = ?", (mission_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Clear error: %s", e)
