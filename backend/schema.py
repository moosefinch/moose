"""
Database schema — all CREATE TABLE statements and migrations.

Called once at startup via init_db().
"""

import sqlite3

from tools import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # RAG sources
    c.execute('''CREATE TABLE IF NOT EXISTS rag_sources (
        url TEXT PRIMARY KEY, title TEXT, domain TEXT, source_type TEXT,
        category TEXT, why_valuable TEXT, content_summary TEXT,
        tags TEXT, stored_at TEXT
    )''')
    # Conversations
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversation_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        role TEXT,
        content TEXT,
        model_label TEXT,
        elapsed_seconds REAL,
        tool_calls TEXT,
        plan TEXT,
        created_at TEXT,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
    )''')
    # Background tasks
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        description TEXT,
        status TEXT DEFAULT 'running',
        plan TEXT,
        progress_log TEXT,
        result TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    # Briefings
    c.execute('''CREATE TABLE IF NOT EXISTS briefings (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        content TEXT,
        created_at TEXT,
        read INTEGER DEFAULT 0,
        FOREIGN KEY (task_id) REFERENCES tasks(id)
    )''')
    # Agent messages (inter-agent communication)
    c.execute('''CREATE TABLE IF NOT EXISTS agent_messages (
        id TEXT PRIMARY KEY,
        msg_type TEXT,
        sender TEXT,
        recipient TEXT,
        mission_id TEXT,
        parent_msg_id TEXT,
        priority INTEGER DEFAULT 1,
        content TEXT,
        payload TEXT,
        created_at TEXT,
        processed_at TEXT
    )''')
    # Workspace entries (shared agent workspace)
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_entries (
        id TEXT PRIMARY KEY,
        mission_id TEXT,
        agent_id TEXT,
        entry_type TEXT,
        title TEXT,
        content TEXT,
        tags TEXT,
        reference_list TEXT,
        created_at TEXT
    )''')
    # Missions
    c.execute('''CREATE TABLE IF NOT EXISTS missions (
        id TEXT PRIMARY KEY,
        status TEXT DEFAULT 'running',
        plan TEXT,
        created_at TEXT,
        completed_at TEXT
    )''')
    # Agent state snapshots
    c.execute('''CREATE TABLE IF NOT EXISTS agent_state (
        agent_id TEXT PRIMARY KEY,
        state TEXT,
        updated_at TEXT
    )''')
    # Channel messages (agent communication channels)
    c.execute('''CREATE TABLE IF NOT EXISTS channel_messages (
        id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        payload TEXT DEFAULT '{}'
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_channel_messages_channel ON channel_messages(channel)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_channel_messages_timestamp ON channel_messages(timestamp)')
    # Desktop actions log
    c.execute('''CREATE TABLE IF NOT EXISTS desktop_actions (
        id TEXT PRIMARY KEY, action TEXT NOT NULL, params TEXT,
        result TEXT, success INTEGER NOT NULL, timestamp REAL NOT NULL,
        reversible INTEGER DEFAULT 0, undo_script TEXT
    )''')
    # Pending approvals
    c.execute('''CREATE TABLE IF NOT EXISTS pending_approvals (
        id TEXT PRIMARY KEY, action TEXT NOT NULL, description TEXT NOT NULL,
        params TEXT, created_at REAL NOT NULL, approved INTEGER
    )''')
    # Temporal snapshots
    c.execute('''CREATE TABLE IF NOT EXISTS temporal_snapshots (
        id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
        state_type TEXT NOT NULL, snapshot_data TEXT NOT NULL,
        confidence REAL DEFAULT 1.0, source TEXT DEFAULT 'system',
        valid_from REAL, valid_to REAL, created_at REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS temporal_scenarios (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, base_snapshot_id TEXT,
        changes TEXT, outcome_analysis TEXT, created_at REAL NOT NULL,
        FOREIGN KEY (base_snapshot_id) REFERENCES temporal_snapshots(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_temporal_entity ON temporal_snapshots(entity_type, entity_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_temporal_valid ON temporal_snapshots(valid_from, valid_to)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_temporal_type ON temporal_snapshots(state_type)')
    # Campaigns
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT DEFAULT 'active',
        target_profile TEXT, strategy_notes TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS prospects (
        id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, company_name TEXT NOT NULL,
        industry TEXT, size TEXT, website TEXT, pain_points TEXT,
        research_notes TEXT, status TEXT DEFAULT 'new', priority TEXT DEFAULT 'medium',
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts (
        id TEXT PRIMARY KEY, prospect_id TEXT NOT NULL, name TEXT NOT NULL,
        title TEXT, email TEXT, role_type TEXT DEFAULT 'unknown', notes TEXT,
        created_at REAL NOT NULL,
        FOREIGN KEY (prospect_id) REFERENCES prospects(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS outreach_attempts (
        id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
        prospect_id TEXT NOT NULL, email_subject TEXT, email_body TEXT,
        status TEXT DEFAULT 'drafted', follow_up_date REAL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS research_dossiers (
        id TEXT PRIMARY KEY, prospect_id TEXT NOT NULL, source_type TEXT NOT NULL,
        source_url TEXT, raw_content TEXT, analysis TEXT, key_findings TEXT,
        confidence REAL DEFAULT 0.7, created_at REAL NOT NULL,
        FOREIGN KEY (prospect_id) REFERENCES prospects(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_prospects_campaign ON prospects(campaign_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_attempts(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_outreach_followup ON outreach_attempts(follow_up_date)')
    # Add sent_at and message_id columns to outreach_attempts (idempotent)
    try:
        c.execute("ALTER TABLE outreach_attempts ADD COLUMN sent_at REAL")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        c.execute("ALTER TABLE outreach_attempts ADD COLUMN message_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Email send log
    c.execute('''CREATE TABLE IF NOT EXISTS email_log (
        id TEXT PRIMARY KEY, outreach_id TEXT NOT NULL,
        event_type TEXT NOT NULL, timestamp REAL NOT NULL,
        details TEXT,
        FOREIGN KEY (outreach_id) REFERENCES outreach_attempts(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_email_log_outreach ON email_log(outreach_id)')
    # Content drafts
    c.execute('''CREATE TABLE IF NOT EXISTS content_drafts (
        id TEXT PRIMARY KEY, content_type TEXT NOT NULL, title TEXT NOT NULL,
        body TEXT, platform TEXT, campaign_id TEXT,
        status TEXT DEFAULT 'drafted', tags TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_content_status ON content_drafts(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_content_type ON content_drafts(content_type)')
    # Add platform_post_id column (idempotent)
    try:
        c.execute("ALTER TABLE content_drafts ADD COLUMN platform_post_id TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Content accounts (future-ready for social API integrations)
    c.execute('''CREATE TABLE IF NOT EXISTS content_accounts (
        id TEXT PRIMARY KEY, platform TEXT NOT NULL, handle TEXT NOT NULL,
        credentials_ref TEXT, active INTEGER DEFAULT 1,
        created_at REAL NOT NULL
    )''')
    # ICP Personas
    c.execute('''CREATE TABLE IF NOT EXISTS icp_personas (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, archetype TEXT NOT NULL,
        description TEXT, industry TEXT, firm_size TEXT,
        pain_points TEXT, talking_points TEXT, compliance_frameworks TEXT,
        email_tone TEXT, preferred_platforms TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    # Marketing cadence configuration
    c.execute('''CREATE TABLE IF NOT EXISTS marketing_cadence (
        id TEXT PRIMARY KEY, loop_type TEXT NOT NULL UNIQUE,
        interval_seconds INTEGER NOT NULL, enabled INTEGER DEFAULT 0,
        last_run REAL, next_run REAL, config TEXT,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cadence_next_run ON marketing_cadence(next_run)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_cadence_enabled ON marketing_cadence(enabled)')
    # Marketing emails (approval pipeline)
    c.execute('''CREATE TABLE IF NOT EXISTS marketing_emails (
        id TEXT PRIMARY KEY, persona_id TEXT, prospect_id TEXT,
        contact_id TEXT, campaign_id TEXT,
        subject TEXT, body TEXT,
        status TEXT DEFAULT 'pending',
        approved_at REAL, rejected_at REAL, sent_at REAL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_marketing_emails_status ON marketing_emails(status)')
    # Scheduled jobs (cron-like self-scheduler)
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled_jobs (
        id TEXT PRIMARY KEY,
        description TEXT,
        schedule_type TEXT,
        schedule_value TEXT,
        agent_id TEXT,
        task_payload TEXT,
        enabled INTEGER DEFAULT 1,
        last_run TEXT,
        next_run TEXT,
        created_at TEXT,
        run_count INTEGER DEFAULT 0
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(next_run)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs(enabled)')
    # Webhook endpoints
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_endpoints (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        source_type TEXT NOT NULL DEFAULT 'generic',
        secret TEXT,
        action_type TEXT NOT NULL DEFAULT 'start_task',
        action_payload TEXT,
        enabled INTEGER DEFAULT 1,
        created_at REAL NOT NULL
    )''')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_slug ON webhook_endpoints(slug)')
    # Webhook log
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_log (
        id TEXT PRIMARY KEY,
        endpoint_id TEXT NOT NULL,
        source_ip TEXT,
        headers TEXT,
        body TEXT,
        action_result TEXT,
        status TEXT DEFAULT 'received',
        created_at REAL NOT NULL,
        FOREIGN KEY (endpoint_id) REFERENCES webhook_endpoints(id)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_webhook_log_endpoint ON webhook_log(endpoint_id)')
    # Rate limits (persistence across restarts)
    c.execute('''CREATE TABLE IF NOT EXISTS rate_limits (
        ip TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        timestamp REAL NOT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_rate_limits_ip ON rate_limits(ip, endpoint)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_rate_limits_ts ON rate_limits(timestamp)')
    # API keys (rotation support)
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        key_hash TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        expires_at REAL,
        active INTEGER DEFAULT 1
    )''')
    # Audit log (security event tracking)
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        timestamp REAL NOT NULL,
        event_type TEXT NOT NULL,
        actor TEXT,
        ip_address TEXT,
        endpoint TEXT,
        method TEXT,
        status_code INTEGER,
        request_summary TEXT,
        metadata TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor)')
    conn.commit()

    # Initialize plugin tables
    from profile import get_profile
    profile = get_profile()
    if profile.plugins.crm.enabled:
        try:
            from plugins.crm import init_db as crm_init_db
            crm_init_db(conn)
        except ImportError:
            pass
    if profile.plugins.telegram.enabled:
        try:
            from plugins.telegram import init_db as tg_init_db
            tg_init_db(conn)
        except ImportError:
            pass
    if profile.plugins.slack.enabled:
        try:
            from plugins.slack import init_db as sl_init_db
            sl_init_db(conn)
        except ImportError:
            pass

    conn.close()
