"""Marketing, campaign, content, persona, and cadence endpoints."""

import json
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core, sanitize_input
from db import db_connection, db_connection_row
from models import (
    MarketingEmailUpdate, PersonaCreate, PersonaUpdate,
    CadenceUpdate, ContentDraftUpdate,
)

router = APIRouter()


# ── Campaigns ──

@router.get("/api/campaigns", dependencies=[Depends(verify_api_key)])
async def list_campaigns():
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


@router.get("/api/campaigns/{campaign_id}", dependencies=[Depends(verify_api_key)])
async def get_campaign_detail(campaign_id: str):
    from tools_outreach import get_campaign_status
    return json.loads(get_campaign_status(campaign_id))


@router.get("/api/campaigns/{campaign_id}/prospects", dependencies=[Depends(verify_api_key)])
async def get_campaign_prospects(campaign_id: str):
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        prospects = conn.execute("SELECT * FROM prospects WHERE campaign_id = ? ORDER BY priority, created_at DESC", (campaign_id,)).fetchall()
        result = []
        for p in prospects:
            cc = conn.execute("SELECT COUNT(*) as c FROM contacts WHERE prospect_id = ?", (p["id"],)).fetchone()["c"]
            oc = conn.execute("SELECT COUNT(*) as c FROM outreach_attempts WHERE prospect_id = ?", (p["id"],)).fetchone()["c"]
            result.append({**dict(p), "contact_count": cc, "outreach_count": oc})
        return result


# ── Marketing Emails ──

@router.get("/api/marketing/emails", dependencies=[Depends(verify_api_key)])
async def list_marketing_emails(status: str = "pending", limit: int = 50):
    limit = min(limit, 100)
    with db_connection_row() as conn:
        q = """SELECT me.*, ct.name as contact_name, ct.email as contact_email,
                      p.company_name as prospect_company
               FROM marketing_emails me
               LEFT JOIN contacts ct ON me.contact_id = ct.id
               LEFT JOIN prospects p ON me.prospect_id = p.id
               WHERE me.status = ?
               ORDER BY me.created_at DESC LIMIT ?"""
        rows = conn.execute(q, (status, limit)).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/marketing/emails/{email_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_marketing_email(email_id: str):
    core = get_core()
    now = time.time()
    with db_connection_row() as conn:
        row = conn.execute("SELECT status FROM marketing_emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Email status is '{row['status']}', expected 'pending'")
        conn.execute("UPDATE marketing_emails SET status = 'approved', approved_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, email_id))
        conn.commit()
    await core.broadcast({"type": "marketing_approval_resolved", "item_type": "email", "id": email_id, "action": "approved"})
    return {"id": email_id, "status": "approved"}


@router.post("/api/marketing/emails/{email_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_marketing_email(email_id: str):
    core = get_core()
    now = time.time()
    with db_connection_row() as conn:
        row = conn.execute("SELECT status FROM marketing_emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Email status is '{row['status']}', expected 'pending'")
        conn.execute("UPDATE marketing_emails SET status = 'rejected', rejected_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, email_id))
        conn.commit()
    await core.broadcast({"type": "marketing_approval_resolved", "item_type": "email", "id": email_id, "action": "rejected"})
    return {"id": email_id, "status": "rejected"}


@router.patch("/api/marketing/emails/{email_id}", dependencies=[Depends(verify_api_key)])
async def edit_marketing_email(email_id: str, req: MarketingEmailUpdate):
    updates = {}
    if req.subject is not None: updates["subject"] = sanitize_input(req.subject, 500)
    if req.body is not None: updates["body"] = sanitize_input(req.body, 10000)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [email_id]
    with db_connection_row() as conn:
        conn.execute(f"UPDATE marketing_emails SET {sc} WHERE id = ?", vals)
        conn.commit()
    return {"id": email_id, "updated": list(updates.keys())}


# ── Marketing Stats ──

@router.get("/api/marketing/stats", dependencies=[Depends(verify_api_key)])
async def marketing_stats():
    with db_connection_row() as conn:
        email_stats = {}
        for row in conn.execute("SELECT status, COUNT(*) as c FROM marketing_emails GROUP BY status").fetchall():
            email_stats[row["status"]] = row["c"]
        content_stats = {}
        for row in conn.execute("SELECT status, COUNT(*) as c FROM content_drafts GROUP BY status").fetchall():
            content_stats[row["status"]] = row["c"]
        persona_count = conn.execute("SELECT COUNT(*) as c FROM icp_personas").fetchone()["c"]
        prospect_count = conn.execute("SELECT COUNT(*) as c FROM prospects").fetchone()["c"]
        cadence_rows = conn.execute("SELECT loop_type, enabled, last_run, next_run FROM marketing_cadence").fetchall()
    return {
        "emails": email_stats,
        "content": content_stats,
        "personas": persona_count,
        "prospects": prospect_count,
        "cadences": [dict(r) for r in cadence_rows],
    }


# ── Marketing Cadences ──

@router.get("/api/marketing/cadences", dependencies=[Depends(verify_api_key)])
async def list_cadences():
    with db_connection_row() as conn:
        rows = conn.execute("SELECT * FROM marketing_cadence ORDER BY loop_type").fetchall()
    return [dict(r) for r in rows]


@router.patch("/api/marketing/cadences/{cadence_id}", dependencies=[Depends(verify_api_key)])
async def update_cadence(cadence_id: str, req: CadenceUpdate):
    updates = {}
    if req.enabled is not None:
        updates["enabled"] = 1 if req.enabled else 0
        if req.enabled:
            updates["next_run"] = time.time()
    if req.interval_seconds is not None:
        if req.interval_seconds < 3600:
            raise HTTPException(status_code=400, detail="Minimum interval is 3600 seconds (1 hour)")
        if req.interval_seconds > 604800:
            raise HTTPException(status_code=400, detail="Maximum interval is 604800 seconds (1 week)")
        updates["interval_seconds"] = req.interval_seconds
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [cadence_id]
    with db_connection_row() as conn:
        conn.execute(f"UPDATE marketing_cadence SET {sc} WHERE id = ?", vals)
        conn.commit()
    return {"id": cadence_id, "updated": list(updates.keys())}


# ── Personas ──

@router.get("/api/personas", dependencies=[Depends(verify_api_key)])
async def list_personas_endpoint():
    from tools_icp import list_personas
    return json.loads(list_personas())


@router.post("/api/personas", dependencies=[Depends(verify_api_key)])
async def create_persona_endpoint(req: PersonaCreate):
    from tools_icp import create_persona
    result = json.loads(create_persona(
        name=sanitize_input(req.name, 200), archetype=sanitize_input(req.archetype, 200),
        description=sanitize_input(req.description or "", 2000), industry=sanitize_input(req.industry or "", 200),
        firm_size=sanitize_input(req.firm_size or "", 100), pain_points=sanitize_input(req.pain_points or "", 2000),
        talking_points=sanitize_input(req.talking_points or "", 2000),
        compliance_frameworks=sanitize_input(req.compliance_frameworks or "", 500),
        email_tone=sanitize_input(req.email_tone or "", 200),
        preferred_platforms=sanitize_input(req.preferred_platforms or "", 500),
    ))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.patch("/api/personas/{persona_id}", dependencies=[Depends(verify_api_key)])
async def update_persona_endpoint(persona_id: str, req: PersonaUpdate):
    from tools_icp import update_persona
    kwargs = {}
    if req.name is not None: kwargs["name"] = sanitize_input(req.name, 200)
    if req.description is not None: kwargs["description"] = sanitize_input(req.description, 2000)
    if req.industry is not None: kwargs["industry"] = sanitize_input(req.industry, 200)
    if req.firm_size is not None: kwargs["firm_size"] = sanitize_input(req.firm_size, 100)
    if req.pain_points is not None: kwargs["pain_points"] = sanitize_input(req.pain_points, 2000)
    if req.talking_points is not None: kwargs["talking_points"] = sanitize_input(req.talking_points, 2000)
    if req.compliance_frameworks is not None: kwargs["compliance_frameworks"] = sanitize_input(req.compliance_frameworks, 500)
    if req.email_tone is not None: kwargs["email_tone"] = sanitize_input(req.email_tone, 200)
    if req.preferred_platforms is not None: kwargs["preferred_platforms"] = sanitize_input(req.preferred_platforms, 500)
    result = json.loads(update_persona(persona_id, **kwargs))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Content Drafts ──

@router.get("/api/content", dependencies=[Depends(verify_api_key)])
async def list_content_drafts(status: str = "", content_type: str = "", limit: int = 50):
    with db_connection_row() as conn:
        q = "SELECT * FROM content_drafts WHERE 1=1"
        params = []
        if status:
            q += " AND status = ?"
            params.append(status)
        if content_type:
            q += " AND content_type = ?"
            params.append(content_type)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/content/{draft_id}", dependencies=[Depends(verify_api_key)])
async def get_content_draft(draft_id: str):
    with db_connection_row() as conn:
        row = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    return dict(row)


@router.patch("/api/content/{draft_id}", dependencies=[Depends(verify_api_key)])
async def update_content_draft_endpoint(draft_id: str, req: ContentDraftUpdate):
    updates = {}
    if req.title is not None: updates["title"] = sanitize_input(req.title, 500)
    if req.body is not None: updates["body"] = sanitize_input(req.body, 50000)
    if req.status is not None: updates["status"] = sanitize_input(req.status, 50)
    if req.tags is not None: updates["tags"] = sanitize_input(req.tags, 500)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [draft_id]
    with db_connection() as conn:
        conn.execute(f"UPDATE content_drafts SET {sc} WHERE id = ?", vals)
        conn.commit()
    return {"id": draft_id, "updated": list(updates.keys())}


@router.delete("/api/content/{draft_id}", dependencies=[Depends(verify_api_key)])
async def delete_content_draft(draft_id: str):
    with db_connection() as conn:
        conn.execute("DELETE FROM content_drafts WHERE id = ?", (draft_id,))
        conn.commit()
    return {"status": "deleted", "id": draft_id}
