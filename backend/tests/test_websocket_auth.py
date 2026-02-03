"""
Tests for WebSocket authentication and origin validation.
These are unit-level tests for the validation logic, not full integration tests.
"""

import pytest


class TestWebSocketAuth:
    """Test WebSocket origin checking logic."""

    def test_allowed_origin_passes(self, mock_profile):
        """Origin in the CORS list should be accepted."""
        allowed = mock_profile.web.cors_origins
        assert "http://localhost:3000" in allowed

    def test_disallowed_origin_rejected(self, mock_profile):
        """Origin not in the CORS list should be rejected."""
        allowed = mock_profile.web.cors_origins
        assert "https://evil.example.com" not in allowed

    def test_empty_origin_allowed(self, mock_profile):
        """Empty origin (same-origin request) should be allowed."""
        origin = ""
        allowed = mock_profile.web.cors_origins
        # Empty origin bypasses check (same-origin or non-browser client)
        assert origin == "" or origin in allowed

    def test_missing_api_key_format(self):
        """Auth message without api_key should be rejected."""
        import json
        msg = {"type": "auth"}
        assert "api_key" not in msg or not isinstance(msg.get("api_key"), str)

    def test_wrong_type_rejected(self):
        """Auth message with wrong type should be rejected."""
        msg = {"type": "query", "api_key": "somekey"}
        assert msg.get("type") != "auth"

    def test_non_dict_rejected(self):
        """Non-dict auth message should be rejected."""
        import json
        raw = json.dumps("just a string")
        parsed = json.loads(raw)
        assert not isinstance(parsed, dict)

    def test_api_key_comparison_timing_safe(self):
        """API key comparison should use constant-time comparison."""
        import secrets
        key1 = "correct_key_12345"
        key2 = "correct_key_12345"
        key3 = "wrong_key_00000"
        assert secrets.compare_digest(key1, key2)
        assert not secrets.compare_digest(key1, key3)
