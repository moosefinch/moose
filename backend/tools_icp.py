"""
ICP Tools — persona management and prospect matching.
"""

import hashlib
import html
import json
import re
import time

from db import db_connection_row


def _gen_id(prefix=""):
    return prefix + hashlib.sha256(f"{prefix}{time.time()}".encode()).hexdigest()[:12]


def _sanitize_text(text: str, max_length: int = 5000) -> str:
    """Strip HTML tags, escape remaining content, enforce length limits."""
    if not text:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Escape any remaining HTML entities
    cleaned = html.escape(cleaned)
    # Enforce length limit
    return cleaned[:max_length]


_VALID_ARCHETYPES = {
    "solo_attorney", "privacy_founder", "small_practice_doctor",
    "freelance_consultant", "small_tax_cpa_firm",
}


def create_persona(name: str, archetype: str, description: str = "",
                   industry: str = "", firm_size: str = "", pain_points: str = "",
                   talking_points: str = "", compliance_frameworks: str = "",
                   email_tone: str = "", preferred_platforms: str = "") -> str:
    """Create an ICP persona. archetype must be one of: solo_attorney, privacy_founder, small_practice_doctor, freelance_consultant, small_tax_cpa_firm."""
    if archetype not in _VALID_ARCHETYPES:
        return json.dumps({"error": f"Invalid archetype. Valid: {sorted(_VALID_ARCHETYPES)}"})
    pid = _gen_id("pers_")
    now = time.time()
    with db_connection_row() as c:
        c.execute("""INSERT INTO icp_personas
                     (id, name, archetype, description, industry, firm_size,
                      pain_points, talking_points, compliance_frameworks,
                      email_tone, preferred_platforms, created_at, updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (pid, _sanitize_text(name, 200), archetype,
                   _sanitize_text(description, 2000), _sanitize_text(industry, 200),
                   _sanitize_text(firm_size, 100), _sanitize_text(pain_points, 2000),
                   _sanitize_text(talking_points, 2000), _sanitize_text(compliance_frameworks, 500),
                   _sanitize_text(email_tone, 500), _sanitize_text(preferred_platforms, 200),
                   now, now))
        c.commit()
    return json.dumps({"persona_id": pid, "name": name, "archetype": archetype})


def list_personas() -> str:
    """List all ICP personas with their details."""
    with db_connection_row() as c:
        rows = c.execute("SELECT * FROM icp_personas ORDER BY name").fetchall()
    personas = [dict(r) for r in rows]
    return json.dumps({"personas": personas, "count": len(personas)})


def get_persona(persona_id: str) -> str:
    """Get detailed info for a single ICP persona."""
    with db_connection_row() as c:
        row = c.execute("SELECT * FROM icp_personas WHERE id = ?", (persona_id,)).fetchone()
    if not row:
        return json.dumps({"error": "Persona not found"})
    return json.dumps(dict(row))


def update_persona(persona_id: str, name: str = "", description: str = "",
                   industry: str = "", firm_size: str = "", pain_points: str = "",
                   talking_points: str = "", compliance_frameworks: str = "",
                   email_tone: str = "", preferred_platforms: str = "") -> str:
    """Update an existing ICP persona's fields."""
    updates = {}
    if name: updates["name"] = _sanitize_text(name, 200)
    if description: updates["description"] = _sanitize_text(description, 2000)
    if industry: updates["industry"] = _sanitize_text(industry, 200)
    if firm_size: updates["firm_size"] = _sanitize_text(firm_size, 100)
    if pain_points: updates["pain_points"] = _sanitize_text(pain_points, 2000)
    if talking_points: updates["talking_points"] = _sanitize_text(talking_points, 2000)
    if compliance_frameworks: updates["compliance_frameworks"] = _sanitize_text(compliance_frameworks, 500)
    if email_tone: updates["email_tone"] = _sanitize_text(email_tone, 500)
    if preferred_platforms: updates["preferred_platforms"] = _sanitize_text(preferred_platforms, 200)
    if not updates:
        return json.dumps({"error": "No fields to update"})
    updates["updated_at"] = time.time()
    sc = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [persona_id]
    with db_connection_row() as c:
        c.execute(f"UPDATE icp_personas SET {sc} WHERE id = ?", vals)
        c.commit()
    return json.dumps({"persona_id": persona_id, "updated": list(updates.keys())})


def match_prospect_to_persona(prospect_id: str) -> str:
    """Match a prospect to the best-fit ICP persona using keyword matching against persona fields. Returns persona_id and match score."""
    with db_connection_row() as c:
        prospect = c.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not prospect:
            return json.dumps({"error": "Prospect not found"})
        personas = c.execute("SELECT * FROM icp_personas").fetchall()
    if not personas:
        return json.dumps({"error": "No personas defined"})

    # Build prospect text for matching
    prospect_text = " ".join([
        prospect["company_name"] or "",
        prospect["industry"] or "",
        prospect["pain_points"] or "",
        prospect["research_notes"] or "",
        prospect["size"] or "",
    ]).lower()

    best_score = 0
    best_persona = None
    for p in personas:
        score = 0
        # Match against persona fields
        match_fields = [
            p["industry"] or "",
            p["pain_points"] or "",
            p["talking_points"] or "",
            p["compliance_frameworks"] or "",
            p["description"] or "",
        ]
        for field in match_fields:
            keywords = [w.strip().lower() for w in field.replace(",", " ").split() if len(w.strip()) > 3]
            for kw in keywords:
                if kw in prospect_text:
                    score += 1
        # Bonus for industry match
        if p["industry"] and p["industry"].lower() in prospect_text:
            score += 5
        if score > best_score:
            best_score = score
            best_persona = p

    if best_persona:
        return json.dumps({
            "persona_id": best_persona["id"],
            "persona_name": best_persona["name"],
            "archetype": best_persona["archetype"],
            "match_score": best_score,
            "pain_points": best_persona["pain_points"],
            "talking_points": best_persona["talking_points"],
        })
    return json.dumps({"error": "No matching persona found", "match_score": 0})


def get_icp_tools() -> list:
    """Return ICP tool functions for registration."""
    return [
        create_persona, list_personas, get_persona,
        update_persona, match_prospect_to_persona,
    ]
