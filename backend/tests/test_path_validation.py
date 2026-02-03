"""
Tests for path validation — ensures traversal and symlink attacks are blocked.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import read_file, write_file, _validate_path, _READ_BLOCKED_PATTERNS, PROJECT_ROOT


class TestPathValidation:
    """Test path traversal prevention and blocked file patterns."""

    def test_traversal_blocked(self):
        result = read_file("../../etc/passwd")
        assert "error" in result.lower()

    def test_absolute_traversal_blocked(self):
        result = read_file("/etc/passwd")
        assert "error" in result.lower()

    def test_read_api_key_blocked(self):
        result = read_file(".moose_api_key")
        assert "blocked" in result.lower()

    def test_read_smtp_config_blocked(self):
        result = read_file(".moose_smtp_config")
        assert "blocked" in result.lower()

    def test_read_env_blocked(self):
        result = read_file(".env")
        assert "blocked" in result.lower()

    def test_read_credentials_blocked(self):
        result = read_file("credentials.json")
        assert "blocked" in result.lower()

    def test_write_main_py_blocked(self):
        result = write_file("main.py", "evil")
        assert "blocked" in result.lower()

    def test_write_config_py_blocked(self):
        result = write_file("config.py", "evil")
        assert "blocked" in result.lower()

    def test_write_tools_py_blocked(self):
        result = write_file("tools.py", "evil")
        assert "blocked" in result.lower()

    def test_validate_path_outside_root(self):
        """Path outside project root should raise ValueError."""
        import pytest
        with pytest.raises(ValueError):
            _validate_path(Path("/tmp/outside_project"))

    def test_dotdot_in_middle(self):
        result = read_file("backend/../../../etc/shadow")
        assert "error" in result.lower()

    def test_blocked_patterns_exist(self):
        """Verify the blocked pattern sets are populated."""
        assert ".moose_api_key" in _READ_BLOCKED_PATTERNS
        assert ".env" in _READ_BLOCKED_PATTERNS
