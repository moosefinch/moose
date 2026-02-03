"""
Tests for AppleScript escaping — ensures no control character injection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools_desktop import _esc


class TestAppleScriptEscaping:
    """Test that _esc strips dangerous characters for AppleScript interpolation."""

    def test_basic_string(self):
        assert _esc("hello world") == "hello world"

    def test_newlines_stripped(self):
        """Newlines could break out of AppleScript strings."""
        result = _esc("hello\nworld")
        assert "\n" not in result
        assert result == "helloworld"

    def test_carriage_return_stripped(self):
        result = _esc("hello\rworld")
        assert "\r" not in result

    def test_tab_stripped(self):
        result = _esc("hello\tworld")
        assert "\t" not in result

    def test_null_bytes_stripped(self):
        result = _esc("hello\x00world")
        assert "\x00" not in result

    def test_backslash_escaped(self):
        result = _esc('hello\\world')
        assert result == 'hello\\\\world'

    def test_double_quote_escaped(self):
        result = _esc('hello"world')
        assert result == 'hello\\"world'

    def test_combined_injection_attempt(self):
        """Simulate AppleScript injection via newline + tell."""
        payload = 'test"\ntell application "Terminal" to do script "rm -rf /"'
        result = _esc(payload)
        assert "\n" not in result
        assert '"' not in result.replace('\\"', '')  # all quotes are escaped

    def test_unicode_preserved(self):
        """Non-control unicode characters should be preserved."""
        result = _esc("hello cafe\u0301")
        assert "cafe" in result

    def test_control_chars_below_32(self):
        """All control characters 0-31 should be stripped."""
        for i in range(32):
            c = chr(i)
            result = _esc(f"a{c}b")
            assert c not in result, f"Control char {i} was not stripped"

    def test_del_character_stripped(self):
        """DEL (127) should be stripped."""
        result = _esc("hello\x7fworld")
        assert "\x7f" not in result

    def test_c1_control_chars_stripped(self):
        """C1 control characters (128-159) should be stripped."""
        for i in range(128, 160):
            c = chr(i)
            result = _esc(f"a{c}b")
            assert c not in result, f"C1 control char {i} was not stripped"

    def test_printable_ascii_preserved(self):
        """All printable ASCII should pass through (with quote/backslash escaping)."""
        safe = "abcABC123 !@#$%^&*()_+-=[]{}|:;'<>,./?"
        result = _esc(safe)
        assert len(result) > 0
        assert "abcABC123" in result

    def test_empty_string(self):
        assert _esc("") == ""

    def test_backslash_sequence_injection(self):
        """Ensure backslash sequences don't create new escape patterns."""
        result = _esc('test\\ninjection')
        assert result == 'test\\\\ninjection'
