"""
Content Tools — draft management for blog posts, social media, landing pages.
"""

import hashlib
import json
import time

from db import db_connection_row


def _gen_id(prefix=""):
    return prefix + hashlib.sha256(f"{prefix}{time.time()}".encode()).hexdigest()[:12]


_PLATFORM_CHAR_LIMITS = {
    "twitter": 280,
    "moltbook": 2000,
    "linkedin": 3000,
    "blog": 50000,
}


def format_for_platform(content: str, platform: str) -> str:
    """Enforce platform character limits. platform: twitter (280), moltbook (2000), linkedin (3000), blog (50000). Truncates at word boundary with ellipsis if needed."""
    limit = _PLATFORM_CHAR_LIMITS.get(platform.lower())
    if not limit:
        return json.dumps({"error": f"Unknown platform. Valid: {sorted(_PLATFORM_CHAR_LIMITS.keys())}"})
    if len(content) <= limit:
        return json.dumps({"content": content, "platform": platform, "chars": len(content), "truncated": False})
    # Truncate at word boundary
    truncated = content[:limit - 1]
    last_space = truncated.rfind(" ")
    if last_space > limit // 2:
        truncated = truncated[:last_space]
    truncated = truncated.rstrip(".,;:!? ") + "\u2026"
    return json.dumps({"content": truncated, "platform": platform, "chars": len(truncated), "truncated": True, "original_chars": len(content)})


def draft_content(content_type: str, title: str, body: str = "", platform: str = "",
                  tags: str = "", campaign_id: str = "") -> str:
    """Store a content draft. content_type: blog_post/social_post/landing_page/email_newsletter/twitter_post/moltbook_post/youtube_script. platform: blog/twitter/linkedin/github/moltbook/youtube."""
    valid_types = {"blog_post", "social_post", "landing_page", "email_newsletter", "twitter_post", "moltbook_post", "youtube_script"}
    if content_type not in valid_types:
        return json.dumps({"error": f"Invalid content_type. Valid: {sorted(valid_types)}"})
    did = _gen_id("cnt_")
    now = time.time()
    with db_connection_row() as c:
        c.execute("""INSERT INTO content_drafts
                     (id, content_type, title, body, platform, campaign_id, status, tags, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,'drafted',?,?,?)""",
                  (did, content_type, title, body, platform, campaign_id, tags, now, now))
        c.commit()
    return json.dumps({"draft_id": did, "content_type": content_type, "title": title, "status": "drafted"})


def list_content_drafts(status: str = "", content_type: str = "", limit: int = 20) -> str:
    """List content drafts with optional filters on status and content_type."""
    with db_connection_row() as c:
        q = "SELECT id, content_type, title, platform, status, tags, created_at, updated_at FROM content_drafts WHERE 1=1"
        params = []
        if status:
            q += " AND status = ?"
            params.append(status)
        if content_type:
            q += " AND content_type = ?"
            params.append(content_type)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(q, params).fetchall()
    drafts = [dict(r) for r in rows]
    return json.dumps({"drafts": drafts, "count": len(drafts)})


def update_content_draft(draft_id: str, title: str = "", body: str = "", status: str = "") -> str:
    """Update a content draft. status: drafted/reviewed/scheduled/published."""
    updates = {}
    if title: updates["title"] = title
    if body: updates["body"] = body
    if status:
        valid_statuses = {"drafted", "reviewed", "scheduled", "published"}
        if status not in valid_statuses:
            return json.dumps({"error": f"Invalid status. Valid: {sorted(valid_statuses)}"})
        updates["status"] = status
    if not updates:
        return json.dumps({"error": "No fields to update"})
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [draft_id]
    with db_connection_row() as c:
        c.execute(f"UPDATE content_drafts SET {sc} WHERE id = ?", vals)
        c.commit()
    return json.dumps({"draft_id": draft_id, "updated": list(updates.keys())})


def get_content_calendar(days: int = 30) -> str:
    """Show scheduled and recently published content within the given number of days."""
    import time as _time
    now = _time.time()
    since = now - (days * 86400)
    with db_connection_row() as c:
        rows = c.execute("""SELECT id, content_type, title, platform, status, tags, created_at, updated_at
                            FROM content_drafts
                            WHERE status IN ('scheduled', 'published') AND updated_at >= ?
                            ORDER BY updated_at DESC""", (since,)).fetchall()
    items = [dict(r) for r in rows]
    return json.dumps({"calendar": items, "count": len(items), "days": days})


def publish_content(draft_id: str) -> str:
    """Mark a content draft as published. If platform is moltbook and API is configured, publishes via API."""
    now = time.time()
    with db_connection_row() as c:
        row = c.execute("SELECT status, title, body, platform, tags FROM content_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            return json.dumps({"error": "Draft not found"})

        platform = row["platform"] or ""
        platform_post_id = None

        # Try to publish via platform API
        if platform.lower() == "moltbook":
            try:
                import asyncio
                from integrations.moltbook import get_moltbook_client
                client = get_moltbook_client()
                if client.is_configured():
                    tags_list = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(
                        client.create_post(
                            body=row["body"] or "",
                            tags=tags_list,
                            title=row["title"] or "",
                        )
                    )
                    if result.get("post_id"):
                        platform_post_id = result["post_id"]
            except Exception as e:
                # Non-fatal — still mark as published locally
                import logging
                logging.getLogger(__name__).warning("Moltbook publish error: %s", e)

        update_sql = "UPDATE content_drafts SET status = 'published', updated_at = ?"
        params = [now]
        if platform_post_id:
            update_sql += ", platform_post_id = ?"
            params.append(platform_post_id)
        update_sql += " WHERE id = ?"
        params.append(draft_id)

        c.execute(update_sql, params)
        c.commit()

    result = {"draft_id": draft_id, "status": "published", "title": row["title"]}
    if platform_post_id:
        result["platform_post_id"] = platform_post_id
    return json.dumps(result)


def get_content_tools() -> list:
    """Return content tool functions for registration."""
    return [
        draft_content, list_content_drafts, update_content_draft,
        get_content_calendar, publish_content, format_for_platform,
    ]
