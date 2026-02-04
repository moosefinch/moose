-- Moose Memory V2 Schema
-- Self-aware, self-populating personal memory system

-- ============================================================================
-- SYSTEM AWARENESS
-- ============================================================================

-- System hardware and capabilities (auto-populated on startup)
CREATE TABLE IF NOT EXISTS system_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Hardware (detected via psutil, platform, etc.)
    hostname TEXT,
    os_type TEXT,                       -- "darwin", "linux", "windows"
    os_version TEXT,
    cpu_model TEXT,
    cpu_cores INTEGER,
    cpu_threads INTEGER,
    ram_total_gb REAL,
    gpu_model TEXT,                     -- NULL if no GPU
    gpu_vram_gb REAL,
    disk_total_gb REAL,

    -- Detected capabilities
    has_gpu INTEGER DEFAULT 0,
    has_neural_engine INTEGER DEFAULT 0,  -- Apple Silicon
    has_cuda INTEGER DEFAULT 0,
    has_rocm INTEGER DEFAULT 0,           -- AMD
    has_metal INTEGER DEFAULT 0,          -- macOS

    -- Derived constraints
    max_model_size_gb REAL,             -- Largest model that fits in memory
    recommended_context_tokens INTEGER, -- Based on available RAM
    can_run_embeddings_locally INTEGER DEFAULT 1,

    -- Last updated
    detected_at REAL DEFAULT (unixepoch()),
    updated_at REAL DEFAULT (unixepoch())
);

-- Real-time resource snapshots (updated periodically)
CREATE TABLE IF NOT EXISTS resource_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL DEFAULT (unixepoch()),

    -- Memory
    ram_used_gb REAL,
    ram_available_gb REAL,
    ram_percent REAL,

    -- CPU
    cpu_percent REAL,
    load_avg_1m REAL,
    load_avg_5m REAL,

    -- GPU (if available)
    gpu_used_gb REAL,
    gpu_available_gb REAL,
    gpu_percent REAL,

    -- Disk
    disk_used_gb REAL,
    disk_available_gb REAL,

    -- Inference backend
    lm_studio_loaded_models TEXT,       -- JSON array
    lm_studio_vram_used_gb REAL,

    -- Moose-specific
    memory_entry_count INTEGER,
    active_sessions INTEGER,
    pending_extractions INTEGER
);

CREATE INDEX IF NOT EXISTS idx_resource_snapshots_time ON resource_snapshots(timestamp DESC);

-- Process inventory (what's running on this machine)
CREATE TABLE IF NOT EXISTS process_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER UNIQUE,
    name TEXT,
    cmdline TEXT,
    cpu_percent REAL,
    memory_mb REAL,
    category TEXT,                      -- "inference", "ide", "browser", "system", "user_app"
    first_seen REAL DEFAULT (unixepoch()),
    last_seen REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_process_inventory_name ON process_inventory(name);
CREATE INDEX IF NOT EXISTS idx_process_inventory_category ON process_inventory(category);

-- ============================================================================
-- USER MODEL
-- ============================================================================

-- User identity (learned, not configured)
CREATE TABLE IF NOT EXISTS user_identity (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Basics (may start NULL, learned over time)
    name TEXT,
    preferred_name TEXT,                -- How they like to be addressed
    timezone TEXT,
    locale TEXT,

    -- Inferred attributes
    role TEXT,                          -- "engineer", "designer", "student", etc.
    experience_level TEXT,              -- "beginner", "intermediate", "advanced", "expert"
    primary_domain TEXT,                -- "robotics", "web", "ml", "embedded", etc.

    -- Communication style (observed)
    verbosity_preference TEXT,          -- "concise", "detailed", "balanced"
    formality_level TEXT,               -- "casual", "professional", "mixed"

    -- Confidence in identity
    identity_confidence REAL DEFAULT 0.0,  -- Grows as we learn more

    created_at REAL DEFAULT (unixepoch()),
    updated_at REAL DEFAULT (unixepoch())
);

-- Style observations for inferring communication preferences
CREATE TABLE IF NOT EXISTS style_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_type TEXT NOT NULL,     -- "message_length", "formality", etc.
    value REAL,
    timestamp REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_style_observations_type ON style_observations(observation_type);
CREATE INDEX IF NOT EXISTS idx_style_observations_time ON style_observations(timestamp DESC);

-- User preferences (accumulated through interaction)
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Categorization
    domain TEXT NOT NULL,               -- "code", "communication", "workflow", "tools", etc.
    scope TEXT DEFAULT 'global',        -- "global", project_id, or specific context

    -- The preference
    key TEXT NOT NULL,                  -- "naming_convention", "indentation", "editor"
    value TEXT NOT NULL,                -- The actual preference

    -- How we know this
    source TEXT DEFAULT 'inferred',     -- "explicit" (user told us), "inferred", "observed"
    evidence TEXT,                      -- What led to this inference
    evidence_count INTEGER DEFAULT 1,   -- How many times we've seen this

    -- Confidence and validity
    confidence REAL DEFAULT 0.5,
    first_observed REAL DEFAULT (unixepoch()),
    last_confirmed REAL DEFAULT (unixepoch()),

    -- For conflict resolution
    contradicted_by INTEGER REFERENCES user_preferences(id),
    active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_user_prefs_domain ON user_preferences(domain);
CREATE INDEX IF NOT EXISTS idx_user_prefs_key ON user_preferences(key);
CREATE INDEX IF NOT EXISTS idx_user_prefs_active ON user_preferences(active) WHERE active = 1;

-- ============================================================================
-- PROJECTS
-- ============================================================================

-- Projects (discovered and tracked)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,                -- Derived from path or name

    -- Basic info
    name TEXT NOT NULL,
    description TEXT,

    -- Location
    path TEXT,                          -- Local filesystem path
    repo_url TEXT,                      -- Git remote if available

    -- Classification
    domain TEXT,                        -- "robotics", "web", "ml", etc.
    project_type TEXT,                  -- "application", "library", "firmware", etc.

    -- Tech stack (auto-detected)
    languages TEXT,                     -- JSON array: ["python", "c++"]
    frameworks TEXT,                    -- JSON array: ["ros2", "react"]
    build_system TEXT,                  -- "cmake", "cargo", "npm", etc.

    -- Status
    status TEXT DEFAULT 'active',       -- "active", "paused", "completed", "archived"
    priority INTEGER DEFAULT 0,

    -- Activity tracking
    first_seen REAL DEFAULT (unixepoch()),
    last_active REAL DEFAULT (unixepoch()),
    interaction_count INTEGER DEFAULT 0,

    -- Detection metadata
    auto_detected INTEGER DEFAULT 0,    -- 1 if we found this ourselves
    detection_source TEXT               -- "cwd", "git", "mentioned", "file_access"
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_last_active ON projects(last_active DESC);
CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);

-- Project-specific knowledge
CREATE TABLE IF NOT EXISTS project_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- What kind of knowledge
    knowledge_type TEXT NOT NULL,       -- "architecture", "convention", "decision", "issue", "solution"

    -- The knowledge
    content TEXT NOT NULL,

    -- Metadata
    file_path TEXT,                     -- If this relates to a specific file
    importance REAL DEFAULT 0.5,

    -- Temporal
    created_at REAL DEFAULT (unixepoch()),
    valid_to REAL,                      -- NULL = still valid
    superseded_by INTEGER REFERENCES project_knowledge(id),

    -- Access tracking
    last_accessed REAL,
    access_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_project_knowledge_project ON project_knowledge(project_id);
CREATE INDEX IF NOT EXISTS idx_project_knowledge_type ON project_knowledge(knowledge_type);

-- ============================================================================
-- EPISODIC MEMORY
-- ============================================================================

-- Core memory table with embeddings
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Content
    content TEXT NOT NULL,
    embedding BLOB,                     -- float32 vector, stored as blob

    -- Classification
    memory_type TEXT NOT NULL,          -- "interaction", "fact", "decision", "outcome", "observation", "summary"
    domain TEXT,                        -- "engineering", "health", "communication", etc.

    -- Importance (adaptive)
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed REAL,

    -- Temporal
    created_at REAL DEFAULT (unixepoch()),
    valid_from REAL,
    valid_to REAL,                      -- NULL = still valid

    -- Linking
    project_id TEXT REFERENCES projects(id),
    session_id TEXT,
    source TEXT DEFAULT 'internal',     -- "internal", "user", "external", "system"

    -- Deduplication
    entity_type TEXT,
    entity_id TEXT,
    superseded_by INTEGER REFERENCES memories(id),

    -- Summarization
    is_summary INTEGER DEFAULT 0,
    summarizes TEXT                     -- JSON array of memory IDs
);

CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
CREATE INDEX IF NOT EXISTS idx_memories_valid ON memories(valid_to) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_memories_entity ON memories(entity_type, entity_id) WHERE entity_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);

-- ============================================================================
-- SESSIONS
-- ============================================================================

-- Conversation sessions
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at REAL DEFAULT (unixepoch()),
    last_message_at REAL,
    message_count INTEGER DEFAULT 0,
    summary TEXT,                       -- Rolling summary of conversation
    active_project_id TEXT REFERENCES projects(id),
    domains_touched TEXT,               -- JSON array of domains discussed
    ended_at REAL
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);

-- Session messages (kept short-term, compressed into memories)
CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                 -- "user", "assistant", "system"
    content TEXT NOT NULL,
    timestamp REAL DEFAULT (unixepoch()),
    extracted INTEGER DEFAULT 0         -- 1 = facts have been extracted from this
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session ON session_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_session_messages_extracted ON session_messages(extracted) WHERE extracted = 0;

-- ============================================================================
-- PATTERNS
-- ============================================================================

-- Observed behavioral patterns
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,         -- "work_habit", "debug_approach", "communication", "schedule", "code_style"
    description TEXT NOT NULL,
    evidence_count INTEGER DEFAULT 1,   -- Times this pattern was observed
    confidence REAL DEFAULT 0.3,        -- Grows with evidence
    first_observed REAL DEFAULT (unixepoch()),
    last_observed REAL DEFAULT (unixepoch()),
    active INTEGER DEFAULT 1            -- 0 = pattern may have changed
);

CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON patterns(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_patterns_active ON patterns(active) WHERE active = 1;

-- Pattern evidence (raw observations that support patterns)
CREATE TABLE IF NOT EXISTS pattern_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id INTEGER REFERENCES patterns(id) ON DELETE CASCADE,
    observation TEXT NOT NULL,
    observed_at REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_pattern_evidence_pattern ON pattern_evidence(pattern_id);

-- ============================================================================
-- DOMAIN EXTENSIONS: ENGINEERING
-- ============================================================================

-- Debug history (what worked, what didn't)
CREATE TABLE IF NOT EXISTS debug_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symptom TEXT NOT NULL,              -- What the problem looked like
    root_cause TEXT,                    -- What it actually was
    solution TEXT,                      -- What fixed it
    domain TEXT,                        -- "ros2", "python", "hardware", etc.
    worked INTEGER DEFAULT 1,           -- 1 = this solution worked
    project_id TEXT REFERENCES projects(id),
    created_at REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_debug_history_domain ON debug_history(domain);
CREATE INDEX IF NOT EXISTS idx_debug_history_worked ON debug_history(worked);
CREATE INDEX IF NOT EXISTS idx_debug_history_project ON debug_history(project_id);

-- Tool preferences
CREATE TABLE IF NOT EXISTS tool_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,             -- "editor", "debugger", "build_system", "vcs", "terminal"
    tool TEXT NOT NULL,                 -- "neovim", "gdb", "cmake", "git"
    context TEXT,                       -- When this applies
    notes TEXT,
    confidence REAL DEFAULT 0.5,
    created_at REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_tool_preferences_category ON tool_preferences(category);

-- Code patterns observed in user's code
CREATE TABLE IF NOT EXISTS code_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,         -- "naming", "structure", "style", "architecture"
    language TEXT,
    description TEXT NOT NULL,
    example TEXT,
    confidence REAL DEFAULT 0.5,
    created_at REAL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_code_patterns_type ON code_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_code_patterns_language ON code_patterns(language);

-- ============================================================================
-- DOMAIN EXTENSIONS: HEALTH (placeholder for future)
-- ============================================================================

-- Health metrics
CREATE TABLE IF NOT EXISTS health_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type TEXT NOT NULL,          -- "sleep", "energy", "exercise", "mood"
    value REAL,
    unit TEXT,
    notes TEXT,
    recorded_at REAL DEFAULT (unixepoch()),
    source TEXT                         -- "manual", "apple_health", "oura", etc.
);

CREATE INDEX IF NOT EXISTS idx_health_metrics_type ON health_metrics(metric_type);
CREATE INDEX IF NOT EXISTS idx_health_metrics_time ON health_metrics(recorded_at DESC);

-- ============================================================================
-- EXTRACTION QUEUE
-- ============================================================================

-- Queue for async fact extraction
CREATE TABLE IF NOT EXISTS extraction_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    session_id TEXT,
    context TEXT,                       -- JSON with additional context
    status TEXT DEFAULT 'pending',      -- "pending", "processing", "completed", "failed"
    created_at REAL DEFAULT (unixepoch()),
    processed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_extraction_queue_status ON extraction_queue(status) WHERE status = 'pending';
