"""
Desktop Control Tools — AppleScript + Vision for Agent system.
Requires macOS Accessibility permissions.
"""

import asyncio
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from config import API_BASE
from inference import InferenceBackend


# Approval flow state
DESTRUCTIVE_ACTIONS = {"close_app", "send_frontmost_email", "type_text", "run_shortcut"}
_pending_approvals: dict[str, dict] = {}
_approval_events: dict[str, asyncio.Event] = {}
_action_log: list[dict] = []
_undo_stack: list[dict] = []
_ws_broadcast = None


def set_ws_broadcast(callback):
    global _ws_broadcast
    _ws_broadcast = callback


def get_pending_approval(approval_id: str):
    return _pending_approvals.get(approval_id)


def resolve_approval(approval_id: str, approved: bool) -> bool:
    if approval_id not in _pending_approvals:
        return False
    _pending_approvals[approval_id]["approved"] = approved
    if approval_id in _approval_events:
        _approval_events[approval_id].set()
    return True


async def _request_approval(action: str, description: str, params: dict) -> bool:
    approval_id = hashlib.sha256(f"{action}{time.time()}".encode()).hexdigest()[:12]
    _pending_approvals[approval_id] = {
        "id": approval_id, "action": action, "description": description,
        "params": params, "created_at": time.time(), "approved": None,
    }
    event = asyncio.Event()
    _approval_events[approval_id] = event
    if _ws_broadcast:
        await _ws_broadcast({
            "type": "approval_request", "id": approval_id,
            "action": action, "description": description, "params": params,
        })
    try:
        await asyncio.wait_for(event.wait(), timeout=120.0)
    except asyncio.TimeoutError:
        _pending_approvals.pop(approval_id, None)
        _approval_events.pop(approval_id, None)
        return False
    result = _pending_approvals[approval_id]["approved"]
    _pending_approvals.pop(approval_id, None)
    _approval_events.pop(approval_id, None)
    return result is True


def _log_action(action, params, result, success, reversible=False, undo_script=None):
    entry = {
        "id": hashlib.sha256(f"{action}{time.time()}".encode()).hexdigest()[:12],
        "action": action, "params": params, "result": result,
        "success": success, "timestamp": time.time(),
        "reversible": reversible, "undo_script": undo_script,
    }
    _action_log.append(entry)
    if len(_action_log) > 500:
        _action_log.pop(0)
    if reversible and undo_script:
        _undo_stack.append(entry)


def _esc(s: str) -> str:
    """Escape a string for safe interpolation into AppleScript double-quoted strings.
    Strips ALL control characters including newlines, tabs, carriage returns,
    and non-printable characters to prevent AppleScript injection."""
    cleaned = ''.join(c for c in s if 32 <= ord(c) < 127 or ord(c) > 159)
    return cleaned.replace('\\', '\\\\').replace('"', '\\"')


def _run_applescript(script: str, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    except Exception as e:
        return False, str(e)


async def _run_applescript_async(script, timeout=10.0):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _run_applescript(script, timeout))


# ── App Control ──

async def open_app(app_name: str) -> dict:
    """Open an application by name."""
    safe = _esc(app_name)
    ok, out = await _run_applescript_async(f'tell application "{safe}" to activate')
    _log_action("open_app", {"app_name": app_name}, out, ok, True, f'tell application "{safe}" to quit')
    return {"success": ok, "output": out}


async def close_app(app_name: str) -> dict:
    """Close an application (requires approval)."""
    if not await _request_approval("close_app", f"Close: {app_name}", {"app_name": app_name}):
        return {"success": False, "output": "Denied"}
    safe = _esc(app_name)
    ok, out = await _run_applescript_async(f'tell application "{safe}" to quit')
    _log_action("close_app", {"app_name": app_name}, out, ok)
    return {"success": ok, "output": out}


async def activate_window(app_name: str) -> dict:
    """Bring an application window to front."""
    safe = _esc(app_name)
    ok, out = await _run_applescript_async(f'tell application "{safe}" to activate')
    _log_action("activate_window", {"app_name": app_name}, out, ok)
    return {"success": ok, "output": out}


async def get_window_list() -> dict:
    """Get list of all open windows."""
    script = '''tell application "System Events"
    set wl to {}
    repeat with proc in (every process whose visible is true)
        try
            repeat with w in (every window of proc)
                set end of wl to name of proc & ": " & name of w
            end repeat
        end try
    end repeat
    return wl
end tell'''
    ok, out = await _run_applescript_async(script, 15.0)
    windows = [w.strip() for w in out.split(",") if w.strip()] if ok and out else []
    _log_action("get_window_list", {}, f"{len(windows)} windows", ok)
    return {"success": ok, "windows": windows}


async def position_window(app_name: str, x: int, y: int, width: int, height: int) -> dict:
    """Position and resize a window."""
    safe = _esc(app_name)
    script = f'''tell application "System Events"
    tell process "{safe}"
        set position of front window to {{{x}, {y}}}
        set size of front window to {{{width}, {height}}}
    end tell
end tell'''
    ok, out = await _run_applescript_async(script)
    _log_action("position_window", {"app_name": app_name, "x": x, "y": y, "width": width, "height": height}, out, ok)
    return {"success": ok, "output": out}


# ── UI Interaction ──

async def click_element(app_name: str, element_description: str) -> dict:
    """Click a UI element via accessibility."""
    script = f'''tell application "System Events"
    tell process "{_esc(app_name)}"
        click {_esc(element_description)}
    end tell
end tell'''
    ok, out = await _run_applescript_async(script)
    _log_action("click_element", {"app_name": app_name, "element": element_description}, out, ok)
    return {"success": ok, "output": out}


async def type_text(text: str) -> dict:
    """Type text into focused app (requires approval). Max 500 characters."""
    if len(text) > 500:
        return {"success": False, "output": "Error: text exceeds 500 character limit"}
    if not await _request_approval("type_text", f"Type: {text[:80]}", {"text": text}):
        return {"success": False, "output": "Denied"}
    safe_text = _esc(text)
    ok, out = await _run_applescript_async(f'tell application "System Events" to keystroke "{safe_text}"')
    _log_action("type_text", {"text": text[:200]}, out, ok)
    return {"success": ok, "output": out}


async def run_shortcut(shortcut_name: str) -> dict:
    """Run a Shortcuts.app shortcut (requires approval)."""
    if not await _request_approval("run_shortcut", f"Run shortcut: {shortcut_name}", {"shortcut_name": shortcut_name}):
        return {"success": False, "output": "Denied"}
    try:
        result = subprocess.run(["shortcuts", "run", shortcut_name], capture_output=True, text=True, timeout=60)
        ok = result.returncode == 0
        out = result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        ok, out = False, str(e)
    _log_action("run_shortcut", {"shortcut_name": shortcut_name}, out, ok)
    return {"success": ok, "output": out}


# ── Vision ──

async def screenshot(region: str = "") -> dict:
    """Take a screenshot. Returns file path."""
    from pathlib import Path
    ss_dir = Path("/tmp/gps_screenshots")
    ss_dir.mkdir(parents=True, exist_ok=True)
    filepath = ss_dir / f"screenshot_{int(time.time())}.png"
    cmd = ["screencapture", "-x"]
    if region:
        cmd.extend(["-R", region])
    cmd.append(str(filepath))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        ok = result.returncode == 0 and filepath.exists()
        out = str(filepath) if ok else result.stderr.strip()
    except Exception as e:
        ok, out = False, str(e)
    _log_action("screenshot", {"region": region}, out, ok)
    return {"success": ok, "path": str(filepath) if ok else None, "output": out}


async def analyze_screen(prompt: str, region: str = "") -> dict:
    """Screenshot + Qwen3-VL vision analysis."""
    shot = await screenshot(region)
    if not shot["success"]:
        return {"success": False, "output": f"Screenshot failed: {shot['output']}"}
    # Use voice model (Qwen3-VL) for vision
    import base64
    img_path = Path(shot["path"])
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    data_url = f"data:image/png;base64,{b64}"
    backend = InferenceBackend(API_BASE)
    from config import MODELS, TOKEN_LIMITS, TEMPERATURE
    model_id = MODELS.get("voice", "")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]
    try:
        resp = await backend.call_llm(model_id, messages, max_tokens=TOKEN_LIMITS.get("voice", 2048), temperature=TEMPERATURE.get("voice", 0.7))
        analysis = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        _log_action("analyze_screen", {"prompt": prompt}, analysis[:200], True)
        return {"success": True, "analysis": analysis, "screenshot_path": shot["path"]}
    except Exception as e:
        return {"success": False, "output": str(e)}


# ── Browser ──

async def open_url(url: str) -> dict:
    """Open a URL in the default browser. Only http:// and https:// schemes are allowed."""
    import re as _re_url
    if not url.startswith("http://") and not url.startswith("https://"):
        return {"success": False, "output": "Error: only http:// and https:// URLs are allowed"}
    # Reject URLs with characters that could break out of AppleScript strings
    # Allow only safe URL characters (RFC 3986 + common query/fragment chars)
    if not _re_url.match(r'^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+$', url):
        return {"success": False, "output": "Error: URL contains invalid characters"}
    if len(url) > 2048:
        return {"success": False, "output": "Error: URL exceeds maximum length"}
    safe_url = _esc(url)
    ok, out = await _run_applescript_async(f'open location "{safe_url}"')
    _log_action("open_url", {"url": url}, out, ok)
    return {"success": ok, "output": out}


async def read_browser_page(prompt: str = "What is on this page?") -> dict:
    """Read current browser page via screenshot + vision."""
    return await analyze_screen(prompt)


# ── Email ──

async def compose_email(to: str, subject: str, body: str) -> dict:
    """Open a draft in Apple Mail for user review."""
    escaped_body = _esc(body).replace('\n', '\\n')
    escaped_subject = _esc(subject)
    safe_to = _esc(to)
    script = f'''tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:"{escaped_subject}", content:"{escaped_body}", visible:true}}
    tell newMsg
        make new to recipient at end of to recipients with properties {{address:"{safe_to}"}}
    end tell
    activate
end tell'''
    ok, out = await _run_applescript_async(script, 15.0)
    _log_action("compose_email", {"to": to, "subject": subject}, out, ok)
    return {"success": ok, "output": out}


async def send_frontmost_email() -> dict:
    """Send frontmost email draft (requires approval)."""
    if not await _request_approval("send_frontmost_email", "Send frontmost email in Apple Mail", {}):
        return {"success": False, "output": "Denied"}
    ok, out = await _run_applescript_async('tell application "Mail" to send front outgoing message')
    _log_action("send_frontmost_email", {}, out, ok)
    return {"success": ok, "output": out}


# ── Safety ──

def get_action_log(limit: int = 50) -> list[dict]:
    """Get recent desktop action log."""
    return _action_log[-limit:]

def get_undo_stack() -> list[dict]:
    """Get reversible actions."""
    return list(_undo_stack)


# ── Tool Registration ──

def get_desktop_tools() -> list:
    """Return desktop tool functions for registration."""
    return [
        open_app, close_app, activate_window, get_window_list, position_window,
        click_element, type_text, run_shortcut,
        screenshot, analyze_screen, open_url, read_browser_page,
        compose_email, send_frontmost_email,
        get_action_log, get_undo_stack,
    ]
