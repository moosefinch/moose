"""
Agent Tools — functions available to model agent loops.
Each function has type hints and a docstring (required by LM Studio SDK).

Tool categories:
  - Primary (exposed to all models): web_search, store_memory, read_file, search_sources
  - Operational (Agent's autonomous capabilities): write_file, list_directory, run_command,
    web_fetch, query_database, catalog_source, recall_memory, search_conversations,
    modify_ui, send_notification, map tools
  - Escalation (internal routing, not in manifest): ask_hermes, ask_claude
"""

import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from config import API_BASE, MODELS, TOKEN_LIMITS, TEMPERATURE, AGENT_TOOL_FILTER
from db import DB_PATH, get_readonly_connection
from tools_desktop import get_desktop_tools
from tools_temporal import get_temporal_tools
from tools_outreach import get_outreach_tools
from tools_content import get_content_tools
from tools_icp import get_icp_tools
from tools_scripting import get_scripting_tools

import logging

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent
ALLOWED_BASE = PROJECT_ROOT.resolve()
WORKSPACE_DIR = (BACKEND_DIR / "workspace").resolve()

# Sensitive paths that agents must never READ (secrets, credentials)
_READ_BLOCKED_PATTERNS = {
    ".gps_api_key", ".gps_smtp_config",
    ".env", ".env.local", ".env.production",
    "credentials.json", "service_account.json",
}

# Sensitive paths that agents must never write to
_WRITE_BLOCKED_PATTERNS = {
    ".gps_api_key", ".gps_smtp_config", "gps.db",
    "main.py", "core.py", "config.py", "inference.py", "db.py",
    "tools.py", "tools_desktop.py", "tools_system.py", "tools_content.py",
    "tools_temporal.py", "tools_icp.py", "tools_outreach.py", "tools_scripting.py",
    "email_sender.py", "memory.py", "cognitive_loop.py",
    "daemon.py", "stt.py", "tts.py", "tts_server.py",
    "com.gps.backend.plist", "start.sh",
}


def _validate_path(p: Path) -> Path:
    """Resolve a path and ensure it's within the project root. Raises ValueError on traversal."""
    resolved = p.resolve()
    if not resolved.is_relative_to(ALLOWED_BASE):
        raise ValueError(f"Path traversal blocked: {resolved} is outside {ALLOWED_BASE}")
    return resolved

# Reference to AgentCore — set at startup
_core = None


def set_core_ref(core_instance):
    """Called at startup to give tools access to AgentCore."""
    global _core
    _core = core_instance


# ── File Operations ──

def read_file(path: str) -> str:
    """Read and return the contents of a file at the given path. Use absolute paths or paths relative to the project root."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        p = _validate_path(p)
    except ValueError as e:
        return f"Error: {e}"
    # Block reads of sensitive files (API keys, credentials, SMTP config)
    if p.name in _READ_BLOCKED_PATTERNS:
        return f"Error: reading '{p.name}' is blocked for security reasons"
    if not p.exists():
        return f"Error: file not found: {p}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > 50000:
            return content[:50000] + f"\n\n[Truncated — file is {len(content)} chars]"
        return content
    except Exception as e:
        return f"Error reading {p}: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file in the workspace directory. Creates parent directories if needed. Paths are resolved relative to backend/workspace/. Writing to backend source, config, or sensitive files is blocked."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    try:
        p = _validate_path(p)
    except ValueError as e:
        return f"Error: {e}"
    # Block writes to sensitive files by name
    if p.name in _WRITE_BLOCKED_PATTERNS:
        return f"Error: writing to '{p.name}' is blocked for security reasons"
    # Block writes to the backend source directory (except workspace/)
    resolved = p.resolve()
    backend_resolved = BACKEND_DIR.resolve()
    if str(resolved).startswith(str(backend_resolved)) and not str(resolved).startswith(str(WORKSPACE_DIR)):
        return f"Error: writing to the backend directory is restricted — use workspace/ instead"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {p}"
    except Exception as e:
        return f"Error writing {p}: {e}"


def list_directory(path: str) -> str:
    """List files and directories at the given path."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        p = _validate_path(p)
    except ValueError as e:
        return f"Error: {e}"
    if not p.exists():
        return f"Error: path not found: {p}"
    if not p.is_dir():
        return f"Not a directory: {p}"
    try:
        entries = sorted(p.iterdir())
        lines = []
        for e in entries:
            kind = "dir" if e.is_dir() else f"{e.stat().st_size}B"
            lines.append(f"  {e.name}  ({kind})")
        return f"{p}/\n" + "\n".join(lines) if lines else f"{p}/ (empty)"
    except Exception as e:
        return f"Error listing {p}: {e}"


# ── Shell ──

# Allowlist of commands that agents may execute — everything else is blocked.
# SECURITY: Only truly read-only / inspection commands are allowed.
# Commands that can execute arbitrary code (python, node, docker, make,
# npm, pip, compilers, sed) are intentionally excluded — an agent could
# write a malicious script to workspace/ then execute it, or install a
# package with post-install hooks, or docker-mount the host filesystem.
_ALLOWED_COMMANDS = {
    # Version control (read-only operations — push/force flags blocked below)
    "git",
    # File inspection (read-only) — cat/head/tail removed; use read_file tool instead
    "ls", "wc", "file", "stat", "du", "df",
    "find", "tree", "basename", "dirname", "realpath",
    # Text processing (read-only, no in-place editing)
    "grep", "rg", "sort", "uniq", "cut", "tr", "diff", "comm",
    "jq", "yq", "xmllint",
    # System info (read-only)
    "uname", "whoami", "hostname", "date", "uptime", "which",
    "sw_vers", "sysctl", "vm_stat",
    # Networking diagnostics (read-only)
    "ping", "dig", "nslookup", "host", "traceroute", "ifconfig",
    # Archive inspection (read-only)
    "zipinfo",
}

# Blocked arguments per command — prevents destructive git operations
_BLOCKED_ARGS: dict[str, set[str]] = {
    "git": {"push", "reset", "clean", "checkout", "restore", "rebase",
            "merge", "cherry-pick", "revert", "rm", "mv",
            "--force", "-f", "--hard"},
    "find": {"-exec", "-execdir", "-delete", "-ok", "-okdir"},
}


def _is_command_safe(command: str) -> tuple[bool, str]:
    """Check if a shell command is safe to execute. Returns (is_safe, reason).

    Uses an allowlist — only explicitly permitted commands may run.
    Shell operators and redirects are blocked to prevent chaining.
    """
    import shlex
    # Reject shell operators that could chain dangerous commands
    for op in ("&&", "||", ";", "|", "`", "$(", "${"):
        if op in command:
            return False, f"Shell operator '{op}' is not allowed — use separate run_command calls"
    # Reject redirects that could overwrite files
    for op in (">", ">>"):
        if op in command:
            return False, f"Redirect '{op}' is not allowed — use write_file instead"
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False, "Could not parse command"
    if not tokens:
        return False, "Empty command"
    base_cmd = Path(tokens[0]).name.lower()
    if base_cmd not in _ALLOWED_COMMANDS:
        return False, f"Command '{base_cmd}' is not in the allowed command list"
    # Check for blocked arguments (code-execution and in-place editing flags)
    blocked = _BLOCKED_ARGS.get(base_cmd)
    if blocked:
        for token in tokens[1:]:
            # Exact match (e.g., "-c", "--eval", "eval")
            if token in blocked:
                return False, f"Argument '{token}' is not allowed for '{base_cmd}'"
            # Combined short flags (e.g., "-ie" contains "-i")
            if token.startswith("-") and not token.startswith("--") and len(token) > 2:
                for flag in blocked:
                    if flag.startswith("-") and not flag.startswith("--") and len(flag) == 2:
                        if flag[1] in token[1:]:
                            return False, f"Flag '{flag}' (in '{token}') is not allowed for '{base_cmd}'"
    return True, ""


def run_command(command: str) -> str:
    """Execute a shell command and return stdout + stderr. Use for git, npm, pip, system commands, etc. Shell operators (&&, ||, ;, |) and redirects (>, >>) are blocked — use separate calls or write_file instead."""
    safe, reason = _is_command_safe(command)
    if not safe:
        return f"Error: {reason}"
    try:
        import shlex
        args = shlex.split(command)
        result = subprocess.run(
            args, capture_output=True, text=True,
            timeout=30, cwd=str(PROJECT_ROOT),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s"
    except Exception as e:
        return f"Error: {e}"


# ── Web ──

def _is_url_safe(url: str) -> tuple[bool, str]:
    """Check if a URL is safe to fetch (no private/internal IPs). Returns (is_safe, reason)."""
    import ipaddress
    import socket
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' is not allowed — only http/https"
    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"
    try:
        # Resolve hostname to IP and check for private ranges
        addr_infos = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False, f"Blocked: {hostname} resolves to private/internal IP {ip}"
    except (socket.gaierror, ValueError):
        return False, f"Cannot resolve hostname: {hostname}"
    return True, ""


async def web_fetch(url: str) -> str:
    """Fetch the contents of a public URL. Returns the response body as text (truncated to 20000 chars). Blocks requests to private/internal IP ranges."""
    safe, reason = _is_url_safe(url)
    if not safe:
        return f"Error: {reason}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            text = resp.text
            if len(text) > 20000:
                text = text[:20000] + f"\n\n[Truncated — response was {len(resp.text)} chars]"
            return f"[{resp.status_code}] {text}"
    except Exception as e:
        return f"Error fetching {url}: {e}"


async def web_search(query: str, engines: str = "", categories: str = "") -> str:
    """Search the web using SearXNG. Returns structured results with title, URL, snippet, and engine. Best results when engines parameter is left empty (uses all available). Optional: categories (e.g. 'general,news,science')."""
    try:
        params = {"q": query, "format": "json"}
        if engines:
            params["engines"] = engines
        if categories:
            params["categories"] = categories
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("http://localhost:8888/search", data=params)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return "No results found."
        output = []
        for r in results[:10]:
            output.append(json.dumps({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
                "engine": r.get("engine", ""),
            }))
        return f"Found {len(results)} results (showing top {min(10, len(results))}):\n" + "\n".join(output)
    except Exception as e:
        return f"Search error: {e}"


# ── Database ──

def query_database(sql: str) -> str:
    """Execute a read-only SQL query against gps.db and return the results as JSON. Only single SELECT statements are allowed. Results limited to 500 rows."""
    if len(sql) > 5000:
        return "Error: query too long (max 5000 chars)."
    sql_clean = sql.strip().rstrip(";")
    # Block multiple statements
    if ";" in sql_clean:
        return "Error: only single SQL statements are allowed."
    sql_upper = sql_clean.upper()
    if not sql_upper.startswith("SELECT"):
        return "Error: only SELECT queries are allowed."
    # Block write operations hidden in subqueries or CTEs
    for keyword in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                     "REPLACE", "ATTACH", "DETACH", "PRAGMA", "REINDEX", "VACUUM",
                     "LOAD_EXTENSION", "SAVEPOINT", "RELEASE"):
        if keyword in sql_upper:
            return f"Error: '{keyword}' is not allowed in read-only queries."
    # Block recursive CTEs that could cause DoS
    if "RECURSIVE" in sql_upper:
        return "Error: recursive queries are not allowed."
    conn = None
    try:
        # Use read-only connection (enforced at SQLite URI level)
        conn = get_readonly_connection()
        cursor = conn.execute(sql_clean)
        # Limit to 500 rows to prevent memory exhaustion
        rows = [dict(row) for row in cursor.fetchmany(500)]
        return json.dumps(rows, indent=2, default=str)
    except Exception as e:
        return f"SQL error: {e}"
    finally:
        if conn:
            conn.close()


# ── Memory ──

async def store_memory(text: str, tags: str = "") -> str:
    """Store a piece of information in Agent's persistent semantic memory. Include relevant tags for categorization."""
    if not _core or not _core.memory:
        return "Error: memory not initialized"
    try:
        idx = await _core.memory.store(text, tags=tags)
        return f"Stored in memory (index {idx}, tags: {tags})"
    except Exception as e:
        return f"Error storing memory: {e}"


async def recall_memory(query: str, count: int = 5) -> str:
    """Search Agent's semantic memory for entries related to the query. Returns the most relevant results."""
    if not _core or not _core.memory:
        return "Error: memory not initialized"
    try:
        results = await _core.memory.search(query, top_k=count)
        if not results:
            return "No relevant memories found."
        lines = []
        for r in results:
            lines.append(f"[{r['score']:.3f}] {r['text'][:200]}")
            if r.get("tags"):
                lines[-1] += f"  (tags: {r['tags']})"
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error searching memory: {e}"


# ── RAG Source Catalog ──

async def catalog_source(url: str, source_type: str, category: str, why_valuable: str, tags: str = "") -> str:
    """Catalog a valuable source for future reference. Call this when you find a noteworthy URL during research. source_type: news, research, government, dataset, tool, reference. category: maritime, cyber, china, finint, geoint, techint. tags: comma-separated additional tags."""
    try:
        # SSRF protection — block private/internal IPs
        safe, reason = _is_url_safe(url)
        if not safe:
            return f"Error: {reason}"

        domain = urlparse(url).netloc or url[:60]
        title = ""
        content_summary = ""

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url)
                text = resp.text[:5000]
                m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
                if m:
                    title = m.group(1).strip()[:200]
                clean = re.sub(r"<[^>]+>", " ", text)
                clean = re.sub(r"\s+", " ", clean).strip()
                content_summary = clean[:500]
        except Exception as e:
            logger.debug("Could not fetch title for %s: %s", url, e)

        if not title:
            title = url[:120]

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO rag_sources (url, title, domain, source_type, category, why_valuable, content_summary, tags, stored_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (url, title, domain, source_type, category, why_valuable, content_summary, tags,
             datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()

        if _core and _core.memory and _core.memory._api_base:
            embed_text = f"SOURCE: {title}\nURL: {url}\nType: {source_type} | Category: {category}\nWhy: {why_valuable}\n{content_summary}"
            combined_tags = ",".join(filter(None, ["rag_source", source_type, category, tags]))
            await _core.memory.store(embed_text, tags=combined_tags)

        return f"Cataloged: {title} ({domain}) — {source_type}/{category}"
    except Exception as e:
        return f"Error cataloging source: {e}"


async def search_sources(query: str, source_type: str = "", category: str = "") -> str:
    """Search the RAG source catalog. Combines semantic memory search with optional filters on source_type and category. Returns matching cataloged sources."""
    results = []

    if _core and _core.memory and _core.memory._api_base:
        try:
            mem_results = await _core.memory.search(f"SOURCE: {query}", top_k=10)
            for r in mem_results:
                if "rag_source" in r.get("tags", ""):
                    results.append({"text": r["text"][:300], "score": r["score"], "source": "memory"})
        except Exception as e:
            logger.debug("Memory search failed during source search: %s", e)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conditions = []
        params = []
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if category:
            conditions.append("category = ?")
            params.append(category)
        like = f"%{query}%"
        conditions.append("(title LIKE ? OR content_summary LIKE ? OR why_valuable LIKE ? OR tags LIKE ?)")
        params.extend([like, like, like, like])
        where = " AND ".join(conditions)
        cursor = conn.execute(
            f"SELECT url, title, domain, source_type, category, why_valuable, tags, stored_at FROM rag_sources WHERE {where} ORDER BY stored_at DESC LIMIT 10",
            params)
        for row in cursor.fetchall():
            results.append({"source": "catalog", **dict(row)})
        conn.close()
    except Exception as e:
        results.append({"error": f"DB search failed: {e}"})

    if not results:
        return "No matching sources found."

    seen_urls = set()
    deduped = []
    for r in results:
        url = r.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(r)

    return json.dumps(deduped[:10], indent=2, default=str)


# ── Notifications ──

async def send_notification(message: str) -> str:
    """Send a notification message to all connected frontend clients via WebSocket."""
    if not _core:
        return "Error: agent core not initialized"
    try:
        await _core.broadcast({"type": "notification", "message": message})
        return f"Notification sent to {len(_core.ws_clients)} clients"
    except Exception as e:
        return f"Error sending notification: {e}"


# ── Map Overlays ──

async def add_map_overlay(overlay_type: str, geojson: str, style: str = "", label: str = "") -> str:
    """Add a geographic overlay to Agent's map. overlay_type: markers, polyline, polygon, circle, heatmap. geojson: valid GeoJSON string. style: JSON string with Leaflet options (color, weight, opacity, fillColor, fillOpacity, radius). label: name for the overlay legend."""
    if not _core:
        return "Error: agent core not initialized"
    overlay_id = str(uuid.uuid4())[:8]
    try:
        geojson_parsed = json.loads(geojson)
    except json.JSONDecodeError:
        return "Error: invalid GeoJSON"
    style_parsed = {}
    if style:
        try:
            style_parsed = json.loads(style)
        except json.JSONDecodeError:
            return "Error: invalid style JSON"

    overlay_data = {
        "id": overlay_id,
        "overlay_type": overlay_type,
        "geojson": geojson_parsed,
        "style": style_parsed,
        "label": label or f"{overlay_type}_{overlay_id}",
    }
    _core._overlays[overlay_id] = overlay_data
    await _core.broadcast({"type": "overlay", "data": overlay_data})
    return f"Overlay added: {overlay_id} ({overlay_type}, label: {overlay_data['label']})"


async def clear_map_overlays(overlay_id: str = "") -> str:
    """Clear map overlays. If overlay_id is provided, clears that specific overlay. If empty, clears all overlays."""
    if not _core:
        return "Error: agent core not initialized"
    if overlay_id:
        _core._overlays.pop(overlay_id, None)
        await _core.broadcast({"type": "clear_overlay", "id": overlay_id})
        return f"Cleared overlay: {overlay_id}"
    else:
        _core._overlays.clear()
        await _core.broadcast({"type": "clear_overlay", "id": ""})
        return "All overlays cleared"


# ── Viewport Control ──

async def push_to_viewport(command: str, url: str = "", metadata: str = "") -> str:
    """Push content to Agent's main viewport display. Commands: load_3d (load a 3D model), show_image (display an image), show_map (switch to map view), show_data (display data), clear (reset to avatar). url: URL of the content to display. metadata: optional JSON metadata."""
    if not _core:
        return "Error: agent core not initialized"
    try:
        payload = {
            "type": "viewport_command",
            "command": command,
            "url": url,
            "metadata": metadata,
        }
        await _core.broadcast(payload)
        return f"Viewport command sent: {command}" + (f" url={url}" if url else "")
    except Exception as e:
        return f"Error pushing to viewport: {e}"


# ── Scheduled Tasks ──

def create_scheduled_job(description: str, schedule_type: str, schedule_value: str,
                         agent_id: str = "", task_payload: str = "") -> str:
    """Create a scheduled job for future execution. Use when users say 'remind me', 'schedule', or 'run this every'. schedule_type: 'interval' (schedule_value=seconds), 'cron' (schedule_value=cron expression), or 'once' (schedule_value=ISO timestamp). agent_id: optional specific agent. task_payload: optional JSON payload."""
    if not _core:
        return "Error: agent core not initialized"
    cron_scheduler = getattr(_core, '_cron_scheduler', None)
    if not cron_scheduler:
        return "Error: cron scheduler not initialized"
    try:
        result = cron_scheduler.create_job(
            description=description,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            agent_id=agent_id,
            task_payload=task_payload,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating scheduled job: {e}"


def schedule_task(description: str, interval_minutes: int = 0,
                  cron_expression: str = "", run_at: str = "") -> str:
    """Schedule a future task for Agent to execute automatically. Provide exactly one of: interval_minutes (recurring every N minutes), cron_expression (e.g. '0 */2 * * *' for every 2 hours), or run_at (ISO timestamp for one-shot execution)."""
    if not _core:
        return "Error: agent core not initialized"
    cron_scheduler = getattr(_core, '_cron_scheduler', None)
    if not cron_scheduler:
        return "Error: cron scheduler not initialized"

    if interval_minutes > 0:
        schedule_type = "interval"
        schedule_value = str(interval_minutes * 60)
    elif cron_expression:
        schedule_type = "cron"
        schedule_value = cron_expression
    elif run_at:
        schedule_type = "once"
        schedule_value = run_at
    else:
        return "Error: provide interval_minutes, cron_expression, or run_at"

    try:
        result = cron_scheduler.create_job(
            description=description,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error scheduling task: {e}"


# ── Model Escalation (internal routing — not exposed in tool manifests) ──

async def ask_hermes(prompt: str) -> str:
    """Ask Hermes 70B for deep reasoning, complex coding, architecture design, or long-form synthesis. Use when a task exceeds your capabilities or needs the bigger brain."""
    if not _core:
        return "Error: agent core not initialized"
    try:
        from agents.prompts import EXECUTOR_PROMPT_HERMES
        SYSTEM_PROMPT = EXECUTOR_PROMPT_HERMES
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API_BASE}/v1/chat/completions",
                json={
                    "model": MODELS["hermes"],
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": TOKEN_LIMITS["hermes"],
                    "temperature": TEMPERATURE["hermes"],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"].get("content", "")
    except Exception as e:
        return f"Error from Hermes: {e}"


_claude_calls_today: list[float] = []
_CLAUDE_DAILY_CAP = 20

async def ask_claude(prompt: str) -> str:
    """Ask Claude Code for the hardest tasks: complex code modifications, multi-file refactors, terminal operations, debugging across codebases. The nuclear option — use sparingly."""
    import asyncio
    if not prompt or not prompt.strip():
        return "Error: empty prompt"
    if len(prompt) > 10_000:
        return f"Error: prompt too long ({len(prompt)} chars, max 10000)"
    # Daily call cap to control costs
    now = time.time()
    day_start = now - 86400
    _claude_calls_today[:] = [t for t in _claude_calls_today if t > day_start]
    if len(_claude_calls_today) >= _CLAUDE_DAILY_CAP:
        return f"Error: daily Claude call limit reached ({_CLAUDE_DAILY_CAP}/day). Try again tomorrow."
    _claude_calls_today.append(now)
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "-", "--max-turns", "1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")), timeout=120
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: Claude timed out after 120s"
        output = stdout.decode().strip()
        if stderr:
            output += f"\n{stderr.decode().strip()}"
        if not output:
            return "(Claude returned no output)"
        if len(output) > 20000:
            output = output[:20000] + "\n\n[Truncated]"
        return output
    except Exception as e:
        return f"Error calling Claude: {e}"


# ── Conversation Search ──

async def search_conversations(query: str) -> str:
    """Search past Agent conversations for relevant context. Uses semantic memory to find related discussion from previous conversations."""
    if not _core or not _core.memory or not _core.memory._api_base:
        return "Error: memory not initialized"
    try:
        results = await _core.memory.search(query, top_k=8)
        conversation_results = [r for r in results if "conversation" in r.get("tags", "")]
        if not conversation_results:
            return "No relevant past conversations found."
        lines = []
        for r in conversation_results:
            lines.append(f"[{r['score']:.3f}] {r['text'][:300]}")
            if r.get("tags"):
                lines[-1] += f"  (tags: {r['tags']})"
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error searching conversations: {e}"


# ── Tool Registry ──

# Escalation tools — only available to Hermes, not during task execution
_ESCALATION_TOOLS = [ask_hermes, ask_claude]


def get_execution_tools() -> list:
    """Return tools available during task execution (no escalation tools).
    Escalation decisions are made by Hermes during planning, not by executor models."""
    return [
        # Primary tools
        web_search,
        store_memory,
        read_file,
        search_sources,
        # Operational tools
        write_file,
        list_directory,
        run_command,
        web_fetch,
        query_database,
        catalog_source,
        recall_memory,
        search_conversations,
        send_notification,
        add_map_overlay,
        clear_map_overlays,
        push_to_viewport,
        schedule_task,
        create_scheduled_job,
        # Desktop tools
    ] + get_desktop_tools() + get_temporal_tools() + get_outreach_tools() + get_content_tools() + get_icp_tools() + get_scripting_tools()


def get_all_tools() -> list:
    """Return all tool functions available to Hermes (includes escalation)."""
    return get_execution_tools() + _ESCALATION_TOOLS


def get_tools_for_agent(agent_id: str) -> list:
    """Return filtered tool list for a specific agent.

    Uses AGENT_TOOL_FILTER from config:
      - None = all execution tools (e.g. hermes)
      - [] = no tools (e.g. reasoner, math)
      - ["tool_a", "tool_b"] = only those tools
    """
    filter_list = AGENT_TOOL_FILTER.get(agent_id)
    if filter_list is None:
        return get_execution_tools()
    if not filter_list:
        return []
    all_exec = get_execution_tools()
    name_set = set(filter_list)
    return [fn for fn in all_exec if fn.__name__ in name_set]
