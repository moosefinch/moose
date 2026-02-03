"""
Script Execution Tool — lets agents write and run scripts with sandbox validation.

Supported interpreters: python3, osascript, bash
Security: AST validation (Python), command blocklist (bash), env stripping, timeouts.
User must approve every script via the existing WebSocket approval flow.
"""

import ast
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──
BACKEND_DIR = Path(__file__).parent
WORKSPACE_DIR = (BACKEND_DIR / "workspace").resolve()

# ── Sandbox Configuration ──
MAX_TIMEOUT = 120
DEFAULT_TIMEOUT = 30
MAX_OUTPUT_BYTES = 50_000

# Allowed interpreters
_ALLOWED_INTERPRETERS = {"python3", "osascript", "bash"}

# ── Python AST Validation ──

# Modules that scripts must never import
_BLOCKED_PYTHON_MODULES = {
    "os", "subprocess", "socket", "shutil", "ctypes",
    "importlib", "sys", "signal", "multiprocessing", "threading",
    "http", "urllib", "requests", "httpx", "ftplib", "smtplib",
    "webbrowser", "code", "codeop", "compileall", "py_compile",
    "pickle", "shelve", "marshal",
}

# Builtin names that scripts must never call
_BLOCKED_PYTHON_BUILTINS = {
    "exec", "eval", "__import__", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit",
    "open",  # block file I/O — scripts should use the agent's write_file tool
}


class ScriptValidationError(Exception):
    """Raised when a script fails sandbox validation."""
    pass


def _validate_python_ast(script: str) -> None:
    """Parse Python script and reject dangerous imports/builtins via AST inspection."""
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        raise ScriptValidationError(f"Python syntax error: {e}")

    for node in ast.walk(tree):
        # Check import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module in _BLOCKED_PYTHON_MODULES:
                    raise ScriptValidationError(
                        f"Blocked import: '{alias.name}' — module '{top_module}' is not allowed"
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_module = node.module.split(".")[0]
                if top_module in _BLOCKED_PYTHON_MODULES:
                    raise ScriptValidationError(
                        f"Blocked import: 'from {node.module}' — module '{top_module}' is not allowed"
                    )

        # Check function calls to blocked builtins
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr

            if name and name in _BLOCKED_PYTHON_BUILTINS:
                raise ScriptValidationError(
                    f"Blocked builtin: '{name}()' is not allowed in sandboxed scripts"
                )

        # Block dunder attribute access (e.g. __class__, __subclasses__)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise ScriptValidationError(
                    f"Blocked attribute: '{node.attr}' — dunder access is not allowed"
                )


# ── Bash Validation ──

_BLOCKED_BASH_COMMANDS = {
    "curl", "wget", "nc", "ncat", "netcat", "socat",
    "rm", "rmdir", "mkfs", "dd", "shred",
    "python", "python3", "node", "ruby", "perl", "php",
    "ssh", "scp", "rsync", "ftp", "sftp", "telnet",
    "sudo", "su", "doas", "pkexec",
    "chmod", "chown", "chgrp",
    "mount", "umount", "diskutil",
    "launchctl", "systemctl", "service",
}

_BLOCKED_BASH_PATTERNS = [
    "| bash", "| sh", "| zsh",
    "$(", "`",  # command substitution
    "> /dev/", ">> /dev/",
    "eval ", "source ",
    "/etc/passwd", "/etc/shadow",
    "~/.ssh", ".bash_history",
]


def _validate_bash_script(script: str) -> None:
    """Check bash script for dangerous commands and patterns."""
    lines = script.strip().splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check for blocked patterns
        for pattern in _BLOCKED_BASH_PATTERNS:
            if pattern in stripped:
                raise ScriptValidationError(
                    f"Line {i}: blocked pattern '{pattern}' is not allowed"
                )

        # Check first token of each command (handle pipes)
        for segment in stripped.split("|"):
            segment = segment.strip()
            if not segment:
                continue
            first_token = segment.split()[0] if segment.split() else ""
            # Strip path prefix (e.g. /usr/bin/curl -> curl)
            base_cmd = Path(first_token).name
            if base_cmd in _BLOCKED_BASH_COMMANDS:
                raise ScriptValidationError(
                    f"Line {i}: command '{base_cmd}' is not allowed"
                )

    # Block rm -rf specifically (even if rm weren't already blocked)
    if "rm -rf" in script or "rm -fr" in script:
        raise ScriptValidationError("'rm -rf' is not allowed")


# ── Environment Stripping ──

_SECRET_ENV_PREFIXES = (
    "GPS_API_KEY", "GPS_SMTP", "GPS_TELEGRAM", "GPS_SLACK",
    "OPENAI_API", "ANTHROPIC_API", "AWS_SECRET", "AWS_ACCESS",
    "GITHUB_TOKEN", "HOMEBREW_GITHUB",
)

_SECRET_ENV_NAMES = {
    "PASSWORD", "SECRET", "TOKEN", "CREDENTIAL",
    "PRIVATE_KEY", "API_KEY",
}


def _make_clean_env() -> dict[str, str]:
    """Return a copy of the environment with secrets stripped."""
    clean = {}
    for key, val in os.environ.items():
        # Skip known secret prefixes
        if any(key.startswith(prefix) for prefix in _SECRET_ENV_PREFIXES):
            continue
        # Skip keys containing secret-like words
        key_upper = key.upper()
        if any(word in key_upper for word in _SECRET_ENV_NAMES):
            continue
        clean[key] = val
    return clean


# ── Script Execution ──

def validate_script(interpreter: str, script: str) -> None:
    """Validate a script before execution. Raises ScriptValidationError on failure."""
    if interpreter not in _ALLOWED_INTERPRETERS:
        raise ScriptValidationError(
            f"Interpreter '{interpreter}' is not allowed. Use: {', '.join(sorted(_ALLOWED_INTERPRETERS))}"
        )

    if not script or not script.strip():
        raise ScriptValidationError("Script is empty")

    if len(script) > 50_000:
        raise ScriptValidationError("Script too large (max 50KB)")

    if interpreter == "python3":
        _validate_python_ast(script)
    elif interpreter == "bash":
        _validate_bash_script(script)
    # osascript: no static validation (AppleScript is relatively sandboxed by macOS)


def create_and_run_script(interpreter: str, script: str,
                          description: str = "", timeout: int = 30) -> str:
    """Write a script, validate it in a sandbox, and execute it. Returns stdout, stderr, and exit code.

    Args:
        interpreter: One of 'python3', 'osascript', or 'bash'.
        script: The script source code to execute.
        description: Human-readable description of what the script does (shown to user for approval).
        timeout: Execution timeout in seconds (default 30, max 120).

    Security: Python scripts are AST-validated to block dangerous imports and builtins.
    Bash scripts are checked for dangerous commands and patterns.
    The environment is stripped of secrets. Working directory is set to workspace/.

    The agent can iterate: if this tool returns an error, write a corrected script and try again.
    """
    # Validate interpreter and script
    try:
        validate_script(interpreter, script)
    except ScriptValidationError as e:
        return f"VALIDATION_ERROR: {e}"

    # Clamp timeout
    timeout = max(1, min(timeout, MAX_TIMEOUT))

    # Write script to a temp file
    suffix = {
        "python3": ".py",
        "bash": ".sh",
        "osascript": ".scpt",
    }.get(interpreter, ".txt")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, dir=str(WORKSPACE_DIR),
            delete=False, prefix="gps_script_",
        ) as f:
            f.write(script)
            script_path = f.name

        # Build command
        if interpreter == "python3":
            cmd = ["python3", script_path]
        elif interpreter == "bash":
            cmd = ["bash", script_path]
        elif interpreter == "osascript":
            cmd = ["osascript", script_path]
        else:
            return f"Error: unsupported interpreter '{interpreter}'"

        # Execute with clean environment
        env = _make_clean_env()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_DIR),
            env=env,
        )

        # Build output
        output_parts = []
        if result.stdout:
            stdout = result.stdout
            if len(stdout) > MAX_OUTPUT_BYTES:
                stdout = stdout[:MAX_OUTPUT_BYTES] + f"\n[Truncated — output was {len(result.stdout)} bytes]"
            output_parts.append(f"STDOUT:\n{stdout}")
        if result.stderr:
            stderr = result.stderr
            if len(stderr) > MAX_OUTPUT_BYTES:
                stderr = stderr[:MAX_OUTPUT_BYTES] + f"\n[Truncated — stderr was {len(result.stderr)} bytes]"
            output_parts.append(f"STDERR:\n{stderr}")

        output_parts.append(f"EXIT_CODE: {result.returncode}")

        return "\n".join(output_parts) if output_parts else f"EXIT_CODE: {result.returncode}\n(no output)"

    except subprocess.TimeoutExpired:
        return f"TIMEOUT: script exceeded {timeout}s limit"
    except Exception as e:
        return f"EXECUTION_ERROR: {e}"
    finally:
        # Clean up temp file
        try:
            os.unlink(script_path)
        except (OSError, UnboundLocalError):
            pass


# ── Tool Registry ──

def get_scripting_tools() -> list:
    """Return the scripting tool functions for registration."""
    return [create_and_run_script]
