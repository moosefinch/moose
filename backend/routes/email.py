"""SMTP and inbound lead capture endpoints."""

import hashlib
import json
import logging
import re as _re
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import verify_api_key, get_core, sanitize_input
from db import db_connection
from models import SmtpTestRequest

logger = logging.getLogger(__name__)

router = APIRouter()


# ── SMTP Status & Test ──

@router.get("/api/smtp/status", dependencies=[Depends(verify_api_key)])
async def smtp_status():
    from email_sender import get_email_sender
    from config import SMTP_ENABLED, SMTP_HOST
    sender = get_email_sender()
    configured = sender.is_configured() if sender else False
    last = sender.last_result.to_dict() if sender and sender.last_result else None
    return {"enabled": SMTP_ENABLED, "configured": configured, "host": SMTP_HOST if configured else None, "last_result": last}


@router.post("/api/smtp/test", dependencies=[Depends(verify_api_key)])
async def smtp_test(req: SmtpTestRequest):
    from email_sender import get_email_sender
    sender = get_email_sender()
    if not sender or not sender.is_configured():
        raise HTTPException(status_code=503, detail="SMTP not configured. Set smtp.enabled in profile.yaml and configure SMTP env vars.")
    from profile import get_profile as _get_smtp_profile
    _smtp_prof = _get_smtp_profile()
    result = await sender.send_email(
        to=req.to_email,
        subject=f"{_smtp_prof.system.name} SMTP Test",
        body=f"This is a test email from {_smtp_prof.system.name}.\n\nIf you received this, SMTP is configured correctly.",
    )
    return result.to_dict()


# ── Inbound Lead Capture ──

_LEAD_RATE_MAX = 5
_LEAD_RATE_WINDOW = 3600  # 1 hour


def _check_lead_rate(ip: str) -> bool:
    now = time.time()
    cutoff = now - _LEAD_RATE_WINDOW
    try:
        with db_connection() as conn:
            conn.execute("DELETE FROM rate_limits WHERE timestamp < ?", (cutoff,))
            count = conn.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE ip = ? AND endpoint = 'lead' AND timestamp > ?",
                (ip, cutoff)).fetchone()[0]
            if count >= _LEAD_RATE_MAX:
                return False
            global_count = conn.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE endpoint = 'lead' AND timestamp > ?",
                (cutoff,)).fetchone()[0]
            if global_count > _LEAD_RATE_MAX * 5:
                return False
            conn.execute("INSERT INTO rate_limits (ip, endpoint, timestamp) VALUES (?, 'lead', ?)",
                         (ip, now))
            conn.commit()
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
    return True


def _validate_email_format(email: str) -> bool:
    """Basic email format validation."""
    return bool(_re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email))


@router.post("/api/leads/inbound")
async def inbound_lead(request: Request):
    """Public endpoint for inbound lead capture. Accepts JSON or form-encoded data."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_lead_rate(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            raw = await request.body()
            if len(raw) > 10_000:
                raise HTTPException(status_code=413, detail="Payload too large")
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
    elif "form" in content_type:
        form = await request.form()
        data = dict(form)
    else:
        raise HTTPException(status_code=400, detail="Content-Type must be application/json or form-encoded")

    # Honeypot field
    if data.get("website_url") or data.get("fax_number"):
        return {"status": "received"}

    name = sanitize_input(str(data.get("name", "")), 200)
    email = str(data.get("email", "")).strip()[:200]
    company = sanitize_input(str(data.get("company", "")), 200)
    phone = sanitize_input(str(data.get("phone", "")), 50)
    message = sanitize_input(str(data.get("message", "")), 2000)
    source = sanitize_input(str(data.get("source", "website")), 100)

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not _validate_email_format(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    now = time.time()
    with db_connection() as conn:
        c = conn.cursor()
        row = c.execute("SELECT id FROM campaigns WHERE name = 'Inbound Leads'").fetchone()
        if row:
            campaign_id = row[0]
        else:
            campaign_id = "camp_" + hashlib.sha256(f"inbound{now}".encode()).hexdigest()[:12]
            c.execute("INSERT INTO campaigns (id, name, status, target_profile, strategy_notes, created_at, updated_at) VALUES (?,?,'active',?,?,?,?)",
                      (campaign_id, "Inbound Leads", "Inbound website leads", "Auto-created for inbound lead capture", now, now))

        prospect_id = "pros_" + hashlib.sha256(f"{email}{now}".encode()).hexdigest()[:12]
        c.execute("INSERT INTO prospects (id, campaign_id, company_name, industry, size, website, pain_points, research_notes, status, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,'new','high',?,?)",
                  (prospect_id, campaign_id, company or "Unknown", "", "", "", message, f"Source: {source}", now, now))

        contact_id = "cont_" + hashlib.sha256(f"{email}{now}c".encode()).hexdigest()[:12]
        c.execute("INSERT INTO contacts (id, prospect_id, name, title, email, role_type, notes, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (contact_id, prospect_id, name or email, "", email, "unknown", f"Phone: {phone}" if phone else "", now))
        conn.commit()

    core = get_core()
    if hasattr(core, '_marketing_engine') and core._marketing_engine:
        await core._marketing_engine.handle_inbound_lead({
            "name": name, "email": email, "company": company,
            "phone": phone, "message": message, "source": source,
        })

    return {"status": "received"}
