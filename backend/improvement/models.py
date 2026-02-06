"""
ImprovementProposal — persistent data model for self-improvement proposals.

Stored in SQLite. Status lifecycle: pending → approved → executing → completed/failed
                                    pending → rejected
"""

import json
import logging
import time
import uuid

from db import db_connection_row

logger = logging.getLogger(__name__)


class ImprovementProposal:
    """A proposal for the system to improve itself (e.g. download a model)."""

    def __init__(
        self,
        id: str | None = None,
        created_at: float | None = None,
        status: str = "pending",
        category: str = "model_download",
        severity: str = "medium",
        gap_description: str = "",
        gap_evidence: dict | None = None,
        solution_type: str = "",
        solution_summary: str = "",
        solution_details: dict | None = None,
        reasoning: str = "",
        approved_at: float | None = None,
        executed_at: float | None = None,
        completed_at: float | None = None,
        execution_log: list[dict] | None = None,
        result: str | None = None,
        error: str | None = None,
    ):
        self.id = id or str(uuid.uuid4())[:12]
        self.created_at = created_at or time.time()
        self.status = status
        self.category = category
        self.severity = severity
        self.gap_description = gap_description
        self.gap_evidence = gap_evidence or {}
        self.solution_type = solution_type
        self.solution_summary = solution_summary
        self.solution_details = solution_details or {}
        self.reasoning = reasoning
        self.approved_at = approved_at
        self.executed_at = executed_at
        self.completed_at = completed_at
        self.execution_log = execution_log or []
        self.result = result
        self.error = error

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "status": self.status,
            "category": self.category,
            "severity": self.severity,
            "gap_description": self.gap_description,
            "gap_evidence": self.gap_evidence,
            "solution_type": self.solution_type,
            "solution_summary": self.solution_summary,
            "solution_details": self.solution_details,
            "reasoning": self.reasoning,
            "approved_at": self.approved_at,
            "executed_at": self.executed_at,
            "completed_at": self.completed_at,
            "execution_log": self.execution_log,
            "result": self.result,
            "error": self.error,
        }

    def log_step(self, message: str):
        """Append a timestamped entry to the execution log."""
        self.execution_log.append({"timestamp": time.time(), "message": message})

    def save(self):
        """Upsert this proposal into the database."""
        with db_connection_row() as conn:
            conn.execute(
                """INSERT INTO improvement_proposals
                   (id, created_at, status, category, severity,
                    gap_description, gap_evidence, solution_type,
                    solution_summary, solution_details, reasoning,
                    approved_at, executed_at, completed_at,
                    execution_log, result, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    approved_at=excluded.approved_at,
                    executed_at=excluded.executed_at,
                    completed_at=excluded.completed_at,
                    execution_log=excluded.execution_log,
                    result=excluded.result,
                    error=excluded.error""",
                (
                    self.id, self.created_at, self.status, self.category,
                    self.severity, self.gap_description,
                    json.dumps(self.gap_evidence), self.solution_type,
                    self.solution_summary, json.dumps(self.solution_details),
                    self.reasoning, self.approved_at, self.executed_at,
                    self.completed_at, json.dumps(self.execution_log),
                    self.result, self.error,
                ),
            )
            conn.commit()

    @classmethod
    def _from_row(cls, row) -> "ImprovementProposal":
        return cls(
            id=row["id"],
            created_at=row["created_at"],
            status=row["status"],
            category=row["category"],
            severity=row["severity"],
            gap_description=row["gap_description"],
            gap_evidence=json.loads(row["gap_evidence"] or "{}"),
            solution_type=row["solution_type"] or "",
            solution_summary=row["solution_summary"] or "",
            solution_details=json.loads(row["solution_details"] or "{}"),
            reasoning=row["reasoning"] or "",
            approved_at=row["approved_at"],
            executed_at=row["executed_at"],
            completed_at=row["completed_at"],
            execution_log=json.loads(row["execution_log"] or "[]"),
            result=row["result"],
            error=row["error"],
        )

    @classmethod
    def load(cls, proposal_id: str) -> "ImprovementProposal | None":
        with db_connection_row() as conn:
            row = conn.execute(
                "SELECT * FROM improvement_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            return cls._from_row(row) if row else None

    @classmethod
    def list_by_status(cls, status: str | None = None) -> list["ImprovementProposal"]:
        with db_connection_row() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM improvement_proposals WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM improvement_proposals ORDER BY created_at DESC"
                ).fetchall()
            return [cls._from_row(r) for r in rows]
