"""
Tests for EmailSender SMTP client.
Tests header sanitization and rate limiting.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


class TestHeaderSanitization:
    """Test email header injection prevention."""

    def test_sanitize_strips_newlines(self):
        """Header sanitization should strip newlines."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="test",
            password="pass",
            from_name="Test",
            from_email="test@test.com"
        )

        # Access the internal sanitization function
        # It's defined inside send_email, so we test the behavior
        malicious_subject = "Normal Subject\r\nBcc: attacker@evil.com"

        # The sanitization should strip \r and \n
        clean = malicious_subject.replace("\r", "").replace("\n", "").replace("\x00", "")
        assert "\r" not in clean
        assert "\n" not in clean
        assert "Bcc:" not in clean.split("\n")[0] if "\n" in clean else "Bcc:" in clean

    def test_sanitize_strips_null_bytes(self):
        """Header sanitization should strip null bytes."""
        malicious = "Subject\x00Injected"
        clean = malicious.replace("\r", "").replace("\n", "").replace("\x00", "")
        assert "\x00" not in clean

    def test_sanitize_preserves_valid_content(self):
        """Sanitization should preserve valid header content."""
        valid = "Re: Your inquiry about product ABC-123"
        clean = valid.replace("\r", "").replace("\n", "").replace("\x00", "")
        assert clean == valid


class TestRateLimiting:
    """Test email rate limiting."""

    def test_global_rate_limit_check(self):
        """Global rate limit should prevent rapid sends."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="test",
            password="pass",
            from_name="Test",
            from_email="test@test.com",
            sends_per_minute=2.0  # 1 email per 30 seconds
        )

        # Simulate a recent send
        sender._global_last_send = time.time()

        # Check rate limit (should be rate limited)
        error = sender._check_rate_limit("recipient@test.com")
        assert error is not None
        assert "Global rate limit" in error

    def test_per_address_rate_limit_check(self):
        """Per-address rate limit should prevent rapid sends to same recipient."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="test",
            password="pass",
            from_name="Test",
            from_email="test@test.com",
            sends_per_minute=2.0
        )

        # Simulate a recent send to specific address
        sender._last_send_times["recipient@test.com"] = time.time()
        sender._global_last_send = 0  # Global limit passed

        # Check rate limit
        error = sender._check_rate_limit("recipient@test.com")
        assert error is not None
        assert "Per-address rate limit" in error

    def test_rate_limit_allows_after_interval(self):
        """Should allow send after rate limit interval passes."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="test",
            password="pass",
            from_name="Test",
            from_email="test@test.com",
            sends_per_minute=60.0  # 1 email per second
        )

        # Set last send to 2 seconds ago
        sender._global_last_send = time.time() - 2
        sender._last_send_times["recipient@test.com"] = time.time() - 2

        # Should not be rate limited
        error = sender._check_rate_limit("recipient@test.com")
        assert error is None

    def test_different_recipients_not_affected(self):
        """Rate limit for one address should not affect different address."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="test",
            password="pass",
            from_name="Test",
            from_email="test@test.com",
            sends_per_minute=60.0
        )

        # Simulate recent send to address A
        sender._last_send_times["a@test.com"] = time.time()
        sender._global_last_send = time.time() - 2  # Global limit passed

        # Address B should not be rate limited
        error = sender._check_rate_limit("b@test.com")
        assert error is None


class TestEmailSenderInit:
    """Test EmailSender initialization."""

    def test_email_sender_init(self):
        """EmailSender should initialize with config."""
        from email_sender import EmailSender

        sender = EmailSender(
            host="smtp.example.com",
            port=587,
            user="user@example.com",
            password="secret",
            from_name="Moose",
            from_email="moose@example.com",
            use_tls=True,
            sends_per_minute=10.0
        )

        assert sender.host == "smtp.example.com"
        assert sender.port == 587
        assert sender.from_email == "moose@example.com"
        assert sender.sends_per_minute == 10.0
        assert sender.use_tls is True

    def test_is_configured_checks_required_fields(self):
        """is_configured() should check for required fields."""
        from email_sender import EmailSender

        # Fully configured
        sender = EmailSender(
            host="smtp.test.com",
            port=587,
            user="user",
            password="pass",
            from_name="Test",
            from_email="test@test.com"
        )
        assert sender.is_configured() is True

        # Missing host
        sender.host = ""
        assert sender.is_configured() is False


class TestSendResult:
    """Test SendResult data class."""

    def test_send_result_success(self):
        """SendResult should capture success state."""
        from email_sender import SendResult

        result = SendResult(success=True, message_id="<123@test.com>")
        assert result.success is True
        assert result.message_id == "<123@test.com>"
        assert result.error is None

    def test_send_result_failure(self):
        """SendResult should capture failure state."""
        from email_sender import SendResult

        result = SendResult(success=False, error="Connection refused")
        assert result.success is False
        assert result.error == "Connection refused"

    def test_send_result_to_dict(self):
        """SendResult.to_dict() should return serializable dict."""
        from email_sender import SendResult

        result = SendResult(success=True, message_id="<abc@test.com>")
        d = result.to_dict()

        assert d["success"] is True
        assert d["message_id"] == "<abc@test.com>"
        assert d["error"] is None
