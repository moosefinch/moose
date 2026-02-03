"""
Outreach Tools — campaign management, prospect research, email drafting.
"""

import asyncio
import hashlib
import json
import time

from db import db_connection, db_connection_row


def _gen_id(prefix=""):
    return prefix + hashlib.sha256(f"{prefix}{time.time()}".encode()).hexdigest()[:12]


# ── Campaign Management ──

def create_campaign(name: str, target_profile: str = "", strategy_notes: str = "") -> str:
    """Create a new outreach campaign. Returns campaign ID."""
    cid = _gen_id("camp_")
    now = time.time()
    with db_connection_row() as c:
        c.execute("INSERT INTO campaigns (id, name, status, target_profile, strategy_notes, created_at, updated_at) VALUES (?,?,'active',?,?,?,?)",
                  (cid, name, target_profile, strategy_notes, now, now))
        c.commit()
    return json.dumps({"campaign_id": cid, "name": name})


def get_campaign_status(campaign_id: str) -> str:
    """Get campaign status with prospect and outreach stats."""
    with db_connection_row() as c:
        cam = c.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not cam:
            return json.dumps({"error": "Campaign not found"})
        pc = c.execute("SELECT COUNT(*) as c FROM prospects WHERE campaign_id = ?", (campaign_id,)).fetchone()["c"]
        stats = c.execute("SELECT status, COUNT(*) as c FROM outreach_attempts WHERE campaign_id = ? GROUP BY status", (campaign_id,)).fetchall()
    return json.dumps({"campaign": {"id": cam["id"], "name": cam["name"], "status": cam["status"],
        "target_profile": cam["target_profile"]}, "prospect_count": pc,
        "outreach_stats": {r["status"]: r["c"] for r in stats}})


def get_next_actions(campaign_id: str = "") -> str:
    """Get prioritized work queue for campaigns."""
    with db_connection_row() as c:
        actions = []
        now = time.time()
        # Follow-ups due
        q = "SELECT oa.*, ct.name as contact_name, p.company_name FROM outreach_attempts oa JOIN contacts ct ON oa.contact_id = ct.id JOIN prospects p ON oa.prospect_id = p.id WHERE oa.follow_up_date <= ? AND oa.status IN ('sent','reviewed')"
        params = [now]
        if campaign_id:
            q += " AND oa.campaign_id = ?"
            params.append(campaign_id)
        for f in c.execute(q, params).fetchall():
            actions.append({"type": "follow_up", "priority": "high", "description": f"Follow up with {f['contact_name']} at {f['company_name']}", "outreach_id": f["id"]})
        # Emails ready to send
        q_ready = "SELECT oa.*, ct.name as contact_name, p.company_name FROM outreach_attempts oa JOIN contacts ct ON oa.contact_id = ct.id JOIN prospects p ON oa.prospect_id = p.id WHERE oa.status = 'reviewed'"
        if campaign_id:
            q_ready += " AND oa.campaign_id = ?"
            for r in c.execute(q_ready, (campaign_id,)).fetchall():
                actions.append({"type": "send_email", "priority": "high", "description": f"Send reviewed email to {r['contact_name']} at {r['company_name']}", "outreach_id": r["id"]})
        else:
            for r in c.execute(q_ready).fetchall():
                actions.append({"type": "send_email", "priority": "high", "description": f"Send reviewed email to {r['contact_name']} at {r['company_name']}", "outreach_id": r["id"]})
        # Drafts pending review
        q2 = "SELECT oa.*, ct.name as contact_name, p.company_name FROM outreach_attempts oa JOIN contacts ct ON oa.contact_id = ct.id JOIN prospects p ON oa.prospect_id = p.id WHERE oa.status = 'drafted'"
        if campaign_id:
            q2 += " AND oa.campaign_id = ?"
            for d in c.execute(q2, (campaign_id,)).fetchall():
                actions.append({"type": "review_draft", "priority": "medium", "description": f"Review draft to {d['contact_name']} at {d['company_name']}", "outreach_id": d["id"]})
        else:
            for d in c.execute(q2).fetchall():
                actions.append({"type": "review_draft", "priority": "medium", "description": f"Review draft to {d['contact_name']} at {d['company_name']}", "outreach_id": d["id"]})
        # Unresearched prospects
        q3 = "SELECT p.* FROM prospects p LEFT JOIN research_dossiers rd ON p.id = rd.prospect_id WHERE rd.id IS NULL AND p.status = 'new'"
        if campaign_id:
            q3 += " AND p.campaign_id = ?"
            for u in c.execute(q3, (campaign_id,)).fetchall():
                actions.append({"type": "research", "priority": "medium", "description": f"Research {u['company_name']}", "prospect_id": u["id"]})
        else:
            for u in c.execute(q3).fetchall():
                actions.append({"type": "research", "priority": "medium", "description": f"Research {u['company_name']}", "prospect_id": u["id"]})
    po = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: po.get(a.get("priority", "medium"), 1))
    return json.dumps({"actions": actions, "count": len(actions)})


# ── Prospect Management ──

def add_prospect(campaign_id: str, company_name: str, industry: str = "", size: str = "",
                 website: str = "", pain_points: str = "", priority: str = "medium") -> str:
    """Add a prospect to a campaign."""
    pid = _gen_id("pros_")
    now = time.time()
    with db_connection_row() as c:
        c.execute("INSERT INTO prospects (id, campaign_id, company_name, industry, size, website, pain_points, research_notes, status, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'','new',?,?,?)",
                  (pid, campaign_id, company_name, industry, size, website, pain_points, priority, now, now))
        c.commit()
    return json.dumps({"prospect_id": pid, "company_name": company_name})


def update_prospect(prospect_id: str, status: str = "", priority: str = "", research_notes: str = "") -> str:
    """Update prospect fields (status, priority, research_notes)."""
    updates = {}
    if status: updates["status"] = status
    if priority: updates["priority"] = priority
    if research_notes: updates["research_notes"] = research_notes
    if not updates:
        return json.dumps({"error": "No fields to update"})
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [prospect_id]
    with db_connection_row() as c:
        c.execute(f"UPDATE prospects SET {sc} WHERE id = ?", vals)
        c.commit()
    return json.dumps({"prospect_id": prospect_id, "updated": list(updates.keys())})


def add_contact(prospect_id: str, name: str, title: str = "", email: str = "",
                role_type: str = "unknown", notes: str = "") -> str:
    """Add a contact to a prospect. role_type: owner/operator/referrer/unknown."""
    cid = _gen_id("cont_")
    with db_connection_row() as c:
        c.execute("INSERT INTO contacts (id, prospect_id, name, title, email, role_type, notes, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (cid, prospect_id, name, title, email, role_type, notes, time.time()))
        c.commit()
    return json.dumps({"contact_id": cid, "name": name})


# ── Research ──

def research_company(prospect_id: str) -> str:
    """Queue research for a prospect. Returns instructions for the agent to use web_search tool with 5 queries."""
    with db_connection_row() as c:
        p = c.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
    if not p:
        return json.dumps({"error": "Prospect not found"})
    company = p["company_name"]
    website = p["website"] or ""
    # Individual/small-biz research queries
    industry = p["industry"] or ""
    queries = [
        f'"{company}" {industry} overview',
        f"site:{website} about" if website else f'"{company}" official website',
        f'"{company}" reviews testimonials',
        f'"{company}" technology tools software',
        f'"{company}" news publications speaking',
    ]
    return json.dumps({"prospect": company, "research_queries": queries,
        "instructions": "Run each query with web_search, then store results with store_research_dossier"})


def store_research_dossier(prospect_id: str, source_type: str, source_url: str = "",
                           raw_content: str = "", analysis: str = "", key_findings: str = "") -> str:
    """Store a research dossier for a prospect."""
    did = _gen_id("dos_")
    with db_connection_row() as c:
        c.execute("INSERT INTO research_dossiers (id, prospect_id, source_type, source_url, raw_content, analysis, key_findings, confidence, created_at) VALUES (?,?,?,?,?,?,?,0.7,?)",
                  (did, prospect_id, source_type, source_url, raw_content, analysis, key_findings, time.time()))
        c.commit()
    return json.dumps({"dossier_id": did})


# ── Email ──

def draft_email(contact_id: str, campaign_id: str, prospect_id: str,
                subject: str, body: str, follow_up_days: int = 7) -> str:
    """Draft an outreach email (stored in DB, not sent)."""
    oid = _gen_id("out_")
    now = time.time()
    fud = now + (follow_up_days * 86400) if follow_up_days > 0 else None
    with db_connection_row() as c:
        c.execute("INSERT INTO outreach_attempts (id, contact_id, campaign_id, prospect_id, email_subject, email_body, status, follow_up_date, created_at, updated_at) VALUES (?,?,?,?,?,?,'drafted',?,?,?)",
                  (oid, contact_id, campaign_id, prospect_id, subject, body, fud, now, now))
        c.commit()
    return json.dumps({"outreach_id": oid, "status": "drafted"})


def update_outreach_status(outreach_id: str, status: str) -> str:
    """Update outreach status: drafted/reviewed/sent/opened/replied/bounced."""
    valid = {"drafted", "reviewed", "sent", "opened", "replied", "bounced"}
    if status not in valid:
        return json.dumps({"error": f"Invalid status. Valid: {sorted(valid)}"})
    with db_connection_row() as c:
        c.execute("UPDATE outreach_attempts SET status = ?, updated_at = ? WHERE id = ?", (status, time.time(), outreach_id))
        c.commit()
    return json.dumps({"outreach_id": outreach_id, "status": status})


# ── Email Send/Review Tools ──

def review_pending_emails(campaign_id: str = "") -> str:
    """List drafted emails awaiting review with preview. Shows subject, recipient, and body preview."""
    with db_connection_row() as c:
        q = """SELECT oa.id, oa.email_subject, oa.email_body, oa.status,
                      ct.name as contact_name, ct.email as contact_email,
                      p.company_name
               FROM outreach_attempts oa
               JOIN contacts ct ON oa.contact_id = ct.id
               JOIN prospects p ON oa.prospect_id = p.id
               WHERE oa.status = 'drafted'"""
        params = []
        if campaign_id:
            q += " AND oa.campaign_id = ?"
            params.append(campaign_id)
        q += " ORDER BY oa.created_at DESC"
        rows = c.execute(q, params).fetchall()
    emails = []
    for r in rows:
        emails.append({
            "outreach_id": r["id"],
            "to": f"{r['contact_name']} <{r['contact_email']}>",
            "company": r["company_name"],
            "subject": r["email_subject"],
            "body_preview": (r["email_body"] or "")[:200],
            "status": r["status"],
        })
    return json.dumps({"pending_emails": emails, "count": len(emails)})


async def approve_and_send_email(outreach_id: str) -> str:
    """Queue a drafted email for human approval. The email will NOT be sent until a human
    approves it via the frontend marketing panel or the /api/marketing/emails/{id}/approve endpoint.
    Updates status to 'reviewed' (pending human approval)."""

    with db_connection_row() as c:
        row = c.execute("""SELECT oa.*, ct.email as contact_email, ct.name as contact_name
                           FROM outreach_attempts oa
                           JOIN contacts ct ON oa.contact_id = ct.id
                           WHERE oa.id = ?""", (outreach_id,)).fetchone()
    if not row:
        return json.dumps({"error": "Outreach attempt not found"})
    if row["status"] not in ("drafted",):
        return json.dumps({"error": f"Cannot queue email with status '{row['status']}'. Must be 'drafted'."})
    if not row["contact_email"]:
        return json.dumps({"error": "Contact has no email address"})

    now = time.time()
    with db_connection_row() as c:
        c.execute("UPDATE outreach_attempts SET status = 'reviewed', updated_at = ? WHERE id = ?",
                  (now, outreach_id))
        c.commit()

    return json.dumps({
        "outreach_id": outreach_id,
        "status": "reviewed",
        "to": row["contact_email"],
        "message": "Email queued for human approval. It will be sent when approved via the marketing panel.",
    })


async def send_campaign_batch(campaign_id: str, max_send: int = 5) -> str:
    """Queue up to N drafted emails in a campaign for human approval. Updates their status to 'reviewed'.
    Emails will NOT be sent until a human approves them via the marketing panel."""

    with db_connection_row() as c:
        rows = c.execute("""SELECT oa.id, oa.email_subject,
                                   ct.email as contact_email, ct.name as contact_name
                            FROM outreach_attempts oa
                            JOIN contacts ct ON oa.contact_id = ct.id
                            WHERE oa.campaign_id = ? AND oa.status = 'drafted'
                            ORDER BY oa.created_at ASC
                            LIMIT ?""", (campaign_id, max_send)).fetchall()

    if not rows:
        return json.dumps({"message": "No drafted emails to queue for approval", "queued": 0})

    queued = 0
    errors = []
    now = time.time()
    for row in rows:
        if not row["contact_email"]:
            errors.append({"outreach_id": row["id"], "error": "No email address"})
            continue

        with db_connection_row() as c:
            c.execute("UPDATE outreach_attempts SET status = 'reviewed', updated_at = ? WHERE id = ?",
                      (now, row["id"]))
            c.commit()
        queued += 1

    return json.dumps({
        "queued": queued,
        "errors": errors,
        "total_attempted": len(rows),
        "message": f"{queued} emails queued for human approval via the marketing panel.",
    })


def schedule_follow_up(outreach_id: str, days: int = 3) -> str:
    """Schedule a follow-up by updating the follow_up_date for a sent email."""
    now = time.time()
    follow_up_date = now + (days * 86400)
    with db_connection_row() as c:
        row = c.execute("SELECT status FROM outreach_attempts WHERE id = ?", (outreach_id,)).fetchone()
        if not row:
            return json.dumps({"error": "Outreach attempt not found"})
        c.execute("UPDATE outreach_attempts SET follow_up_date = ?, updated_at = ? WHERE id = ?",
                  (follow_up_date, now, outreach_id))
        c.commit()
    return json.dumps({"outreach_id": outreach_id, "follow_up_days": days, "follow_up_date": follow_up_date})


def get_outreach_tools() -> list:
    """Return outreach tool functions for registration."""
    return [
        create_campaign, get_campaign_status, get_next_actions,
        add_prospect, update_prospect, add_contact,
        research_company, store_research_dossier, draft_email, update_outreach_status,
        review_pending_emails, approve_and_send_email, send_campaign_batch, schedule_follow_up,
    ]
