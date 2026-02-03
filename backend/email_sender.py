"""
Email Sender — async SMTP sending for Moose outreach.
Plain text only. Rate limited. List-Unsubscribe header for compliance.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"success": self.success, "message_id": self.message_id, "error": self.error}


class EmailSender:
    """Async SMTP email sender with rate limiting."""

    def __init__(self, host: str, port: int, user: str, password: str,
                 from_name: str, from_email: str, use_tls: bool = True,
                 sends_per_minute: float = 2.0):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_name = from_name
        self.from_email = from_email
        self.use_tls = use_tls
        self.sends_per_minute = sends_per_minute
        self._last_send_times: dict[str, float] = {}  # per-address rate tracking
        self._global_last_send: float = 0.0
        self._lock = asyncio.Lock()
        self.last_result: Optional[SendResult] = None

    def _check_rate_limit(self, to_address: str) -> Optional[str]:
        """Check if we can send to this address. Returns error string if rate limited."""
        now = time.time()
        min_interval = 60.0 / self.sends_per_minute

        # Global rate limit
        if now - self._global_last_send < min_interval:
            wait = min_interval - (now - self._global_last_send)
            return f"Global rate limit: wait {wait:.1f}s"

        # Per-address rate limit
        last = self._last_send_times.get(to_address, 0)
        if now - last < min_interval:
            wait = min_interval - (now - last)
            return f"Per-address rate limit for {to_address}: wait {wait:.1f}s"

        return None

    async def send_email(self, to: str, subject: str, body: str,
                         reply_to: str = None) -> SendResult:
        """Send a plain text email via SMTP.

        Returns SendResult with success status, message_id, and any error.
        """
        try:
            import aiosmtplib
        except ImportError:
            return SendResult(success=False, error="aiosmtplib not installed. Run: pip install aiosmtplib")

        async with self._lock:
            # Check rate limit
            rate_error = self._check_rate_limit(to)
            if rate_error:
                return SendResult(success=False, error=rate_error)

            message_id = f"<{uuid.uuid4()}@{self.from_email.split('@')[-1] if '@' in self.from_email else 'moose.local'}>"

            # Sanitize headers — strip characters that could inject additional headers
            def _sanitize_header(value: str) -> str:
                return value.replace("\r", "").replace("\n", "").replace("\x00", "")

            safe_to = _sanitize_header(to)
            safe_subject = _sanitize_header(subject)
            safe_from_name = _sanitize_header(self.from_name)

            # Build email manually for full header control
            from email.mime.text import MIMEText
            msg = MIMEText(body, "plain", "utf-8")
            msg["From"] = f"{safe_from_name} <{self.from_email}>"
            msg["To"] = safe_to
            msg["Subject"] = safe_subject
            msg["Message-ID"] = message_id
            msg["List-Unsubscribe"] = f"<mailto:{self.from_email}?subject=unsubscribe>"
            if reply_to:
                msg["Reply-To"] = reply_to

            try:
                if self.use_tls:
                    await aiosmtplib.send(
                        msg,
                        hostname=self.host,
                        port=self.port,
                        username=self.user,
                        password=self.password,
                        start_tls=True,
                    )
                else:
                    await aiosmtplib.send(
                        msg,
                        hostname=self.host,
                        port=self.port,
                        username=self.user,
                        password=self.password,
                    )

                now = time.time()
                self._global_last_send = now
                self._last_send_times[to] = now

                result = SendResult(success=True, message_id=message_id)
                self.last_result = result
                logger.info("[EmailSender] Sent to %s: %s (id: %s)", to, subject, message_id)
                return result

            except Exception as e:
                result = SendResult(success=False, error=str(e))
                self.last_result = result
                logger.error("[EmailSender] Failed to send to %s: %s", to, e)
                return result

    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(self.host and self.user and self.password and self.from_email)


# Module-level sender instance — initialized from config
_sender: Optional[EmailSender] = None


def get_email_sender() -> Optional[EmailSender]:
    """Get or create the global email sender from config."""
    global _sender
    if _sender is not None:
        return _sender

    from config import (
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
        SMTP_FROM_NAME, SMTP_FROM_EMAIL, SMTP_USE_TLS,
        SMTP_ENABLED, SMTP_SENDS_PER_MINUTE,
    )

    if not SMTP_ENABLED:
        return None

    _sender = EmailSender(
        host=SMTP_HOST,
        port=SMTP_PORT,
        user=SMTP_USER,
        password=SMTP_PASSWORD,
        from_name=SMTP_FROM_NAME,
        from_email=SMTP_FROM_EMAIL,
        use_tls=SMTP_USE_TLS,
        sends_per_minute=SMTP_SENDS_PER_MINUTE,
    )
    return _sender
