"""Webhook/event trigger endpoints."""

import hashlib
import hmac
import json
import logging
import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import verify_api_key, get_core
from models import WebhookCreate, WebhookUpdate
from tools import DB_PATH

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Authenticated CRUD ──

@router.get("/api/webhooks", dependencies=[Depends(verify_api_key)])
async def list_webhooks():
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM webhook_endpoints ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/api/webhooks", dependencies=[Depends(verify_api_key)])
async def create_webhook(req: WebhookCreate):
    conn = _get_conn()
    try:
        # Check slug uniqueness
        existing = conn.execute("SELECT id FROM webhook_endpoints WHERE slug = ?", (req.slug,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Slug '{req.slug}' already in use")

        wh_id = f"wh_{uuid.uuid4().hex[:12]}"
        now = time.time()
        conn.execute(
            """INSERT INTO webhook_endpoints
               (id, name, slug, source_type, secret, action_type, action_payload, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (wh_id, req.name, req.slug, req.source_type, req.secret or "",
             req.action_type, req.action_payload or "", now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM webhook_endpoints WHERE id = ?", (wh_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.patch("/api/webhooks/{wh_id}", dependencies=[Depends(verify_api_key)])
async def update_webhook(wh_id: str, req: WebhookUpdate):
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM webhook_endpoints WHERE id = ?", (wh_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Webhook not found")

        updates = req.model_dump(exclude_none=True)
        if not updates:
            return dict(row)

        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [wh_id]
        conn.execute(f"UPDATE webhook_endpoints SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM webhook_endpoints WHERE id = ?", (wh_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/api/webhooks/{wh_id}", dependencies=[Depends(verify_api_key)])
async def delete_webhook(wh_id: str):
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM webhook_endpoints WHERE id = ?", (wh_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"status": "deleted", "id": wh_id}
    finally:
        conn.close()


# ── Public Receiver (HMAC-verified) ──

@router.post("/api/webhooks/receive/{slug}")
async def receive_webhook(slug: str, request: Request):
    """Public endpoint — receives incoming webhook payloads."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM webhook_endpoints WHERE slug = ? AND enabled = 1", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Webhook not found or disabled")

        endpoint = dict(row)

        # Read body
        raw_body = await request.body()
        try:
            body = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"raw": raw_body.decode("utf-8", errors="replace")[:2000]}

        # HMAC verification if secret is set
        secret = endpoint.get("secret", "")
        if secret:
            sig_header = request.headers.get("x-hub-signature-256", "")
            if not sig_header:
                sig_header = request.headers.get("x-signature", "")
            if not sig_header:
                _log_webhook(conn, endpoint["id"], request, body, "Missing signature header", "rejected")
                raise HTTPException(status_code=403, detail="Missing signature")
            expected = "sha256=" + hmac.new(
                secret.encode(), raw_body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                _log_webhook(conn, endpoint["id"], request, body, "HMAC verification failed", "rejected")
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse payload by source type
        from webhook_handlers import parse_github_webhook, parse_generic_webhook, substitute_template

        headers_dict = dict(request.headers)
        if endpoint["source_type"] == "github":
            parsed = parse_github_webhook(headers_dict, body)
        else:
            parsed = parse_generic_webhook(body)

        # Execute action
        core = get_core()
        action_type = endpoint["action_type"]
        action_payload = endpoint.get("action_payload", "")

        # Template substitution
        if action_payload:
            action_payload = substitute_template(action_payload, parsed)

        action_result = ""
        try:
            if action_type == "start_task":
                description = action_payload or parsed.get("summary", "Webhook trigger")
                task = await core.start_task(description)
                action_result = f"Task started: {task.id}"

            elif action_type == "chat":
                message = action_payload or parsed.get("summary", "Webhook event received")
                result = await core.chat(message, history=[])
                action_result = f"Chat response: {result.get('content', '')[:200]}"

            elif action_type == "notify":
                message = action_payload or parsed.get("summary", "Webhook event")
                await core.broadcast({
                    "type": "notification",
                    "message": f"[Webhook: {endpoint['name']}] {message}",
                })
                action_result = "Notification sent"

            else:
                action_result = f"Unknown action type: {action_type}"

        except Exception as e:
            action_result = f"Action error: {e}"
            logger.error("Webhook action failed: %s", e)

        # Log the webhook
        _log_webhook(conn, endpoint["id"], request, body, action_result, "processed")

        return {
            "status": "processed",
            "event_type": parsed.get("event_type", "unknown"),
            "summary": parsed.get("summary", ""),
            "action_result": action_result,
        }

    finally:
        conn.close()


def _log_webhook(conn, endpoint_id: str, request: Request, body: dict,
                 action_result: str, status: str):
    """Log a webhook event to the webhook_log table."""
    try:
        log_id = f"whl_{uuid.uuid4().hex[:12]}"
        source_ip = request.client.host if request.client else ""
        headers_str = json.dumps(dict(request.headers), default=str)[:4000]
        body_str = json.dumps(body, default=str)[:8000]

        conn.execute(
            """INSERT INTO webhook_log
               (id, endpoint_id, source_ip, headers, body, action_result, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, endpoint_id, source_ip, headers_str, body_str,
             action_result[:2000], status, time.time()),
        )
        conn.commit()
    except Exception as e:
        logger.debug("Failed to log webhook: %s", e)
