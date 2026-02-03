"""
Audit Logger — Security event tracking for Moose.
Logs security-relevant events to the audit_log table.
"""

import json
import logging
import time
import uuid
from typing import Optional

from db import db_connection

logger = logging.getLogger(__name__)


class AuditLogger:
    """Log security-relevant events to audit_log table."""

    # Known event types for validation
    EVENT_TYPES = {
        "auth_success",
        "auth_failure",
        "key_rotation",
        "task_start",
        "task_complete",
        "escalation_requested",
        "escalation_approved",
        "escalation_denied",
        "file_access",
        "file_write",
        "shell_command",
        "email_sent",
        "rate_limit_hit",
        "security_flag",
        "api_request",
        "websocket_connect",
        "websocket_disconnect",
    }

    @staticmethod
    def log(
        event_type: str,
        actor: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        request_summary: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Log an audit event to the database.

        Args:
            event_type: Type of event (should be in EVENT_TYPES)
            actor: Who performed the action (user ID, agent ID, or "system")
            ip_address: Client IP address
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            status_code: HTTP response status code
            request_summary: Brief description of the request (truncated to 500 chars)
            metadata: Additional context as JSON-serializable dict
        """
        if event_type not in AuditLogger.EVENT_TYPES:
            logger.warning("Unknown audit event type: %s", event_type)

        entry_id = f"aud_{uuid.uuid4().hex[:12]}"

        try:
            with db_connection() as conn:
                conn.execute(
                    """INSERT INTO audit_log
                       (id, timestamp, event_type, actor, ip_address, endpoint,
                        method, status_code, request_summary, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry_id,
                        time.time(),
                        event_type,
                        actor,
                        ip_address,
                        endpoint,
                        method,
                        status_code,
                        (request_summary or "")[:500],
                        json.dumps(metadata) if metadata else None,
                    ),
                )
                conn.commit()
        except Exception as e:
            # Don't let audit failures break the application
            logger.error("Audit log failed: %s", e)

    @staticmethod
    def query(
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query audit log entries.

        Args:
            event_type: Filter by event type
            actor: Filter by actor
            since: Filter events after this timestamp
            limit: Maximum entries to return

        Returns:
            List of audit log entries as dicts
        """
        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        if since:
            conditions.append("timestamp > ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        try:
            with db_connection() as conn:
                conn.row_factory = lambda c, r: dict(
                    zip([col[0] for col in c.description], r)
                )
                rows = conn.execute(
                    f"""SELECT * FROM audit_log {where}
                        ORDER BY timestamp DESC LIMIT ?""",
                    params,
                ).fetchall()
                return rows
        except Exception as e:
            logger.error("Audit query failed: %s", e)
            return []


# Module-level convenience function
def audit(event_type: str, **kwargs):
    """Convenience function for logging audit events."""
    AuditLogger.log(event_type, **kwargs)


# Convenience functions for common events
def audit_auth_success(ip_address: str, endpoint: str):
    """Log successful authentication."""
    audit("auth_success", ip_address=ip_address, endpoint=endpoint)


def audit_auth_failure(ip_address: str, endpoint: str, reason: str = None):
    """Log failed authentication."""
    audit(
        "auth_failure",
        ip_address=ip_address,
        endpoint=endpoint,
        metadata={"reason": reason} if reason else None,
    )


def audit_rate_limit(ip_address: str, endpoint: str):
    """Log rate limit hit."""
    audit("rate_limit_hit", ip_address=ip_address, endpoint=endpoint)


def audit_security_flag(message: str, ip_address: str = None, metadata: dict = None):
    """Log a security flag/warning."""
    audit(
        "security_flag",
        ip_address=ip_address,
        request_summary=message,
        metadata=metadata,
    )
