"""
Tests for shell command allowlist — ensures dangerous commands and operators are blocked.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import run_command, _is_command_safe


class TestShellCommands:
    """Test shell command safety checks."""

    def test_ls_allowed(self):
        safe, _ = _is_command_safe("ls -la")
        assert safe

    def test_git_log_allowed(self):
        safe, _ = _is_command_safe("git log --oneline -5")
        assert safe

    def test_git_push_blocked(self):
        safe, reason = _is_command_safe("git push origin main")
        assert not safe
        assert "push" in reason

    def test_git_force_blocked(self):
        safe, reason = _is_command_safe("git reset --force")
        assert not safe

    def test_python_blocked(self):
        safe, reason = _is_command_safe("python -c 'import os; os.system(\"rm -rf /\")'")
        assert not safe

    def test_cat_blocked(self):
        """cat was removed from allowed commands — agents use read_file instead."""
        safe, reason = _is_command_safe("cat /etc/passwd")
        assert not safe
        assert "not in the allowed" in reason

    def test_head_blocked(self):
        safe, reason = _is_command_safe("head -n 10 /etc/passwd")
        assert not safe

    def test_tail_blocked(self):
        safe, reason = _is_command_safe("tail -f /var/log/system.log")
        assert not safe

    def test_pipe_blocked(self):
        safe, reason = _is_command_safe("ls | grep secret")
        assert not safe
        assert "|" in reason

    def test_semicolon_blocked(self):
        safe, reason = _is_command_safe("ls; rm -rf /")
        assert not safe
        assert ";" in reason

    def test_and_operator_blocked(self):
        safe, reason = _is_command_safe("ls && rm -rf /")
        assert not safe
        assert "&&" in reason

    def test_redirect_blocked(self):
        safe, reason = _is_command_safe("echo evil > /etc/passwd")
        assert not safe
        assert ">" in reason

    def test_backtick_blocked(self):
        safe, reason = _is_command_safe("ls `rm -rf /`")
        assert not safe

    def test_dollar_paren_blocked(self):
        safe, reason = _is_command_safe("ls $(rm -rf /)")
        assert not safe

    def test_make_blocked(self):
        safe, _ = _is_command_safe("make install")
        assert not safe

    def test_npm_blocked(self):
        safe, _ = _is_command_safe("npm install evil-package")
        assert not safe

    def test_empty_command(self):
        safe, reason = _is_command_safe("")
        assert not safe

    def test_grep_allowed(self):
        safe, _ = _is_command_safe("grep -r pattern .")
        assert safe

    def test_wc_allowed(self):
        safe, _ = _is_command_safe("wc -l file.txt")
        assert safe
