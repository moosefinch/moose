"""
Webhook payload handlers — parse incoming webhook payloads by source type.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_github_webhook(headers: dict, body: dict) -> dict:
    """Extract event type and summary from GitHub webhook payload.

    Returns dict with: event_type, summary, repo, sender, action.
    """
    event_type = headers.get("x-github-event", "unknown")
    repo = ""
    sender = ""
    action = ""
    summary = ""

    if isinstance(body, dict):
        repo_data = body.get("repository", {})
        repo = repo_data.get("full_name", "") if isinstance(repo_data, dict) else ""
        sender_data = body.get("sender", {})
        sender = sender_data.get("login", "") if isinstance(sender_data, dict) else ""
        action = body.get("action", "")

        if event_type == "push":
            commits = body.get("commits", [])
            count = len(commits)
            ref = body.get("ref", "").replace("refs/heads/", "")
            summary = f"Push to {repo}/{ref}: {count} commit(s)"
            if commits:
                summary += f" — latest: {commits[-1].get('message', '')[:100]}"

        elif event_type == "pull_request":
            pr = body.get("pull_request", {})
            title = pr.get("title", "") if isinstance(pr, dict) else ""
            number = pr.get("number", "") if isinstance(pr, dict) else ""
            summary = f"PR #{number} {action}: {title}"

        elif event_type == "issues":
            issue = body.get("issue", {})
            title = issue.get("title", "") if isinstance(issue, dict) else ""
            number = issue.get("number", "") if isinstance(issue, dict) else ""
            summary = f"Issue #{number} {action}: {title}"

        elif event_type == "release":
            release = body.get("release", {})
            tag = release.get("tag_name", "") if isinstance(release, dict) else ""
            summary = f"Release {action}: {tag}"

        else:
            summary = f"GitHub {event_type}"
            if action:
                summary += f" ({action})"
            summary += f" on {repo}" if repo else ""

    return {
        "event_type": event_type,
        "summary": summary or f"GitHub webhook: {event_type}",
        "repo": repo,
        "sender": sender,
        "action": action,
    }


def parse_generic_webhook(body: dict) -> dict:
    """Pass-through parser for generic webhooks. Extracts a truncated summary."""
    summary = ""
    if isinstance(body, dict):
        # Try common fields
        for key in ("message", "text", "content", "description", "summary", "event"):
            if key in body:
                summary = str(body[key])[:500]
                break
        if not summary:
            summary = json.dumps(body, default=str)[:500]
    else:
        summary = str(body)[:500]

    return {
        "event_type": "generic",
        "summary": summary,
    }


def substitute_template(template: str, context: dict) -> str:
    """Substitute template variables like {summary}, {event_type} in action payloads."""
    result = template
    for key, value in context.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result
