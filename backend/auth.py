"""
Authentication and input sanitization utilities.

Provides API key loading, verification dependency, readiness check,
and shared input sanitization used across route modules.
"""

import os
import re as _re
import html as _html
import secrets
from pathlib import Path

from fastapi import Request, HTTPException

from core import AgentCore


_API_KEY_PATH = Path(__file__).parent / ".moose_api_key"


def _load_or_create_api_key() -> str:
    if _API_KEY_PATH.exists():
        return _API_KEY_PATH.read_text().strip()
    key = secrets.token_urlsafe(32)
    _API_KEY_PATH.write_text(key)
    _API_KEY_PATH.chmod(0o600)
    return key


MOOSE_API_KEY = os.environ.get("MOOSE_API_KEY") or _load_or_create_api_key()


def verify_api_key(request: Request):
    """Dependency that checks for a valid API key in the X-API-Key header."""
    key = request.headers.get("x-api-key")
    if not key or not secrets.compare_digest(key, MOOSE_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_ready(request: Request):
    """Dependency that returns 503 if Agent core is still initializing."""
    core = request.app.state.agent_core
    if not core._ready:
        raise HTTPException(status_code=503, detail="Agent core is still initializing")


_app_ref = None


def set_app(app):
    """Called by main.py after app creation to avoid circular imports."""
    global _app_ref
    _app_ref = app


def get_core() -> AgentCore:
    """Return the AgentCore instance from app state."""
    return _app_ref.state.agent_core


def sanitize_input(text: str, max_length: int = 5000) -> str:
    """Strip HTML tags and enforce length limits on user input."""
    if not text:
        return ""
    cleaned = _re.sub(r"<[^>]+>", "", text)
    cleaned = _html.escape(cleaned)
    return cleaned[:max_length]
