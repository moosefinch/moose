"""
CRM Plugin — outreach, content creation, campaign management, and ICP targeting.

This plugin provides:
  - Outreach and Content agents
  - Campaign, prospect, content, and ICP tools
  - Marketing and outreach engines
  - CRM database tables
  - Marketing API endpoints
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

PLUGIN_ID = "crm"


def get_agents() -> list:
    """Return agent classes provided by this plugin."""
    from agents.outreach import OutreachAgent
    from agents.content import ContentAgent
    return [OutreachAgent, ContentAgent]


def get_tools() -> list:
    """Return tool functions provided by this plugin."""
    tools = []
    try:
        from tools_outreach import (
            create_campaign, list_campaigns, add_prospect,
            research_company, draft_email, get_campaign_status,
        )
        tools.extend([
            create_campaign, list_campaigns, add_prospect,
            research_company, draft_email, get_campaign_status,
        ])
    except ImportError:
        logger.warning("CRM plugin: tools_outreach not available")

    try:
        from tools_content import (
            draft_content, list_content_drafts, publish_content,
            format_for_platform,
        )
        tools.extend([
            draft_content, list_content_drafts, publish_content,
            format_for_platform,
        ])
    except ImportError:
        logger.warning("CRM plugin: tools_content not available")

    try:
        from tools_icp import list_personas, create_persona, update_persona
        tools.extend([list_personas, create_persona, update_persona])
    except ImportError:
        logger.warning("CRM plugin: tools_icp not available")

    return tools


def get_router():
    """Return FastAPI APIRouter for CRM endpoints, or None."""
    # CRM endpoints are currently defined inline in main.py.
    # They will be extracted to this plugin in a future refactor.
    return None


def init_db(conn) -> None:
    """Create CRM-specific database tables."""
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS outreach_attempts (
        id TEXT PRIMARY KEY, campaign_id TEXT, prospect_id TEXT,
        subject TEXT, body TEXT, status TEXT DEFAULT 'draft',
        sent_at REAL, follow_up_date TEXT, follow_up_count INTEGER DEFAULT 0,
        response_received INTEGER DEFAULT 0, response_date TEXT,
        message_id TEXT, notes TEXT,
        created_at REAL, updated_at REAL,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
        FOREIGN KEY (prospect_id) REFERENCES prospects(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_attempts(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_outreach_followup ON outreach_attempts(follow_up_date)')

    # Add columns idempotently
    for col, ctype in [("sent_at", "REAL"), ("message_id", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE outreach_attempts ADD COLUMN {col} {ctype}")
        except Exception:
            pass

    c.execute('''CREATE TABLE IF NOT EXISTS email_log (
        id TEXT PRIMARY KEY, outreach_id TEXT NOT NULL,
        direction TEXT DEFAULT 'outbound', subject TEXT, body TEXT,
        sent_at REAL, status TEXT DEFAULT 'sent',
        FOREIGN KEY (outreach_id) REFERENCES outreach_attempts(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_email_log_outreach ON email_log(outreach_id)')

    c.execute('''CREATE TABLE IF NOT EXISTS content_drafts (
        id TEXT PRIMARY KEY, content_type TEXT, title TEXT, body TEXT,
        platform TEXT, status TEXT DEFAULT 'draft',
        platform_post_id TEXT,
        created_at REAL, updated_at REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_content_status ON content_drafts(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_content_type ON content_drafts(content_type)')

    try:
        c.execute("ALTER TABLE content_drafts ADD COLUMN platform_post_id TEXT")
    except Exception:
        pass

    c.execute('''CREATE TABLE IF NOT EXISTS icp_personas (
        id TEXT PRIMARY KEY, name TEXT, archetype TEXT,
        description TEXT, industry TEXT, firm_size TEXT,
        pain_points TEXT, talking_points TEXT, compliance_frameworks TEXT,
        email_tone TEXT, preferred_platforms TEXT,
        created_at REAL, updated_at REAL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS marketing_cadence (
        id TEXT PRIMARY KEY, loop_type TEXT, interval_seconds INTEGER,
        enabled INTEGER DEFAULT 1, last_run REAL, next_run REAL,
        config TEXT, created_at REAL, updated_at REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cadence_next_run ON marketing_cadence(next_run)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cadence_enabled ON marketing_cadence(enabled)')

    c.execute('''CREATE TABLE IF NOT EXISTS marketing_emails (
        id TEXT PRIMARY KEY, prospect_id TEXT, campaign_id TEXT,
        subject TEXT, body TEXT, status TEXT DEFAULT 'pending',
        created_at REAL, updated_at REAL,
        approved_at REAL, rejected_at REAL, sent_at REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_marketing_emails_status ON marketing_emails(status)')

    conn.commit()


_marketing_engine = None


async def start(agent_core) -> None:
    """Start the CRM plugin — initialize marketing engine."""
    global _marketing_engine
    try:
        from marketing_engine import get_marketing_engine
        _marketing_engine = get_marketing_engine()
        _marketing_engine.set_ws_broadcast(agent_core.broadcast)
        _marketing_engine.set_task_creator(lambda desc: agent_core.start_task(desc))
        await _marketing_engine.start()
        logger.info("CRM plugin started")
    except Exception as e:
        logger.error("CRM plugin start failed: %s", e)


async def stop() -> None:
    """Stop the CRM plugin — shut down marketing engine."""
    global _marketing_engine
    if _marketing_engine:
        await _marketing_engine.stop()
        _marketing_engine = None
    logger.info("CRM plugin stopped")
