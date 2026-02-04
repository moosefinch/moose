"""
Configuration — centralized settings for the entire backend.
All user-configurable values come from profile.yaml via get_profile().
Execution limits and internal constants remain as code constants.
"""

import os
from pathlib import Path as _Path

from profile import get_profile

_profile = get_profile()

# ── Inference Backend ──
# Default endpoint from profile; individual backends managed by InferenceRouter.
_default_backend = _profile.get_backend("default")
API_HOST = "localhost"
API_PORT = 1234
API_BASE = _default_backend.endpoint if _default_backend else "http://localhost:1234"

# ── Model IDs from profile ──
MODELS = {}
MODEL_LABELS = {}
MODEL_VRAM_GB = {}
MODEL_TIERS = {}  # model_key -> "always_loaded" | "on_demand"

_model_map = {
    "hermes": _profile.inference.models.primary,
    "conversational": _profile.inference.models.conversational,
    "orchestrator": _profile.inference.models.orchestrator,
    "classifier": _profile.inference.models.classifier,
    "security": _profile.inference.models.security,
    "embedder": _profile.inference.models.embedder,
}
for key, mcfg in _model_map.items():
    if mcfg.model_id:
        MODELS[key] = mcfg.model_id
        MODEL_LABELS[key] = f"{mcfg.model_id} ({key})"
        MODEL_TIERS[key] = getattr(mcfg, "tier", "on_demand")
        if mcfg.vram_gb:
            MODEL_VRAM_GB[key] = mcfg.vram_gb

# ── Memory Strategy (dynamic — derived from profile tier settings) ──
ALWAYS_LOADED_MODELS = {k for k, t in MODEL_TIERS.items() if t == "always_loaded"}
MANAGED_MODELS = {k for k, t in MODEL_TIERS.items() if t == "on_demand"}
LARGE_MODELS = {k for k in MANAGED_MODELS if MODEL_VRAM_GB.get(k, 0) > 20}

# ── Execution Limits (code constants — not user config) ──
DEFAULT_TIMEOUT = 300
MAX_TOOL_ROUNDS = 8
MAX_SECURITY_CONSULTATIONS = 5

# ── Token Limits per model ──
TOKEN_LIMITS = {
    "hermes": _profile.inference.models.primary.max_tokens or 4096,
    "conversational": _profile.inference.models.conversational.max_tokens or 2048,
    "orchestrator": _profile.inference.models.orchestrator.max_tokens or 1024,
    "classifier": _profile.inference.models.classifier.max_tokens or 10,
    "security": _profile.inference.models.security.max_tokens or 4096,
    "planner": 4096,
    "default": 2048,
}

# ── Temperature defaults ──
TEMPERATURE = {
    "hermes": _profile.inference.models.primary.temperature or 0.7,
    "conversational": _profile.inference.models.conversational.temperature or 0.7,
    "orchestrator": _profile.inference.models.orchestrator.temperature or 0.3,
    "classifier": _profile.inference.models.classifier.temperature or 0.1,
    "security": _profile.inference.models.security.temperature or 0.3,
    "planner": 0.3,
    "default": 0.7,
}

# ── Context Window ──
CONTEXT_WINDOW_SIZE = 6

# ── Classifier ──
CLASSIFIER_MODEL = "classifier"
CLASSIFIER_MAX_TOKENS = 32
CLASSIFIER_TEMPERATURE = 0.1
TRIVIAL_RESPONSE_MAX_TOKENS = 256
TRIVIAL_RESPONSE_TEMPERATURE = 0.7

# ── Persistent State ──
STATE_DIR = _Path(__file__).parent / "memory"
STATE_FILE_PATH = STATE_DIR / "state.json"
SOUL_FILE_PATH = STATE_DIR / "SOUL.md"

# ── SMTP Configuration from profile ──
SMTP_HOST = os.environ.get("MOOSE_SMTP_HOST", _profile.smtp.host)
SMTP_PORT = int(os.environ.get("MOOSE_SMTP_PORT", str(_profile.smtp.port)))
SMTP_USER = os.environ.get("MOOSE_SMTP_USER", _profile.smtp.user)
SMTP_PASSWORD = os.environ.get("MOOSE_SMTP_PASSWORD", _profile.smtp.password)
SMTP_FROM_NAME = os.environ.get("MOOSE_SMTP_FROM_NAME", _profile.smtp.from_name)
SMTP_FROM_EMAIL = os.environ.get("MOOSE_SMTP_FROM_EMAIL", _profile.smtp.from_email)
SMTP_USE_TLS = _profile.smtp.use_tls
SMTP_ENABLED = _profile.smtp.enabled or os.environ.get("MOOSE_SMTP_ENABLED", "false").lower() == "true"
SMTP_SENDS_PER_MINUTE = _profile.smtp.sends_per_minute

# ── Agent Definitions (dynamic — only enabled agents) ──
ESCALATION_CONFIG = {
    "require_user_approval": True,
    "targets": {
        "user": {
            "label": "Handle it yourself",
            "description": "Presents findings so far and asks for your guidance",
            "memory_cost": 0,
            "always_available": True,
        },
        "claude": {
            "label": "Send to Claude (API)",
            "description": "External API call, no local memory impact",
            "memory_cost": 0,
            "always_available": False,
        },
    },
}

# Base agent definitions — full catalog
_ALL_AGENT_DEFINITIONS = {
    "hermes": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": True,
        "capabilities": [
            "deep_reasoning", "execution", "tool_calling",
            "security_escalation", "complex_analysis",
        ],
    },
    "classifier": {
        "model_key": "classifier",
        "model_size": "small",
        "can_use_tools": False,
        "capabilities": ["classification", "routing"],
    },
    "security": {
        "model_key": "security",
        "model_size": "small",
        "can_use_tools": False,
        "capabilities": [
            "security_monitor", "consultation", "sanitization",
            "continuous_audit", "osint", "cyber", "exploit_analysis",
        ],
    },
    "coder": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": True,
        "capabilities": [
            "code_generation", "debugging", "refactoring", "code_review",
            "engineering", "3d_modeling", "3d_printing", "scripting",
        ],
    },
    "math": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": False,
        "capabilities": ["math", "logic", "data_analysis", "statistics"],
    },
    "reasoner": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": True,
        "capabilities": ["planning", "reasoning", "analysis", "tool_calling", "escalation_detection"],
    },
    "outreach": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": True,
        "capabilities": [
            "prospect_discovery", "company_research", "email_drafting",
            "campaign_management", "outreach_strategy",
        ],
    },
    "content": {
        "model_key": "hermes",
        "model_size": "small",
        "can_use_tools": True,
        "capabilities": [
            "blog_writing", "social_media", "landing_pages",
            "content_strategy", "copywriting",
        ],
    },
    "claude": {
        "model_key": "claude",
        "model_size": "external",
        "can_use_tools": False,
        "capabilities": ["code", "refactoring", "debugging", "terminal"],
    },
}

# Dynamic: only include agents where profile.agents.<key>.enabled is true
# Outreach and content agents are included when the CRM plugin is enabled
AGENT_DEFINITIONS = {}
for agent_id, defn in _ALL_AGENT_DEFINITIONS.items():
    if agent_id in ("outreach", "content"):
        # CRM agents: only if CRM plugin is enabled
        if _profile.plugins.crm.enabled:
            AGENT_DEFINITIONS[agent_id] = defn
    elif _profile.is_agent_enabled(agent_id):
        AGENT_DEFINITIONS[agent_id] = defn

# ── Per-Agent Tool Filtering ──
AGENT_TOOL_FILTER = {
    "outreach": [
        "create_campaign", "get_campaign_status", "get_next_actions",
        "add_prospect", "update_prospect", "add_contact",
        "research_company", "store_research_dossier", "draft_email",
        "update_outreach_status", "web_search", "web_fetch",
        "store_memory", "recall_memory",
        "review_pending_emails", "approve_and_send_email",
        "send_campaign_batch", "schedule_follow_up",
        "create_persona", "list_personas", "get_persona",
        "update_persona", "match_prospect_to_persona",
    ],
    "coder": [
        "read_file", "write_file", "list_directory", "run_command",
        "web_search", "web_fetch", "query_database",
        "store_memory", "recall_memory",
        "open_app", "close_app", "activate_window", "get_window_list",
        "position_window", "click_element", "type_text", "run_shortcut",
        "screenshot", "analyze_screen", "open_url", "read_browser_page",
        "compose_email", "send_frontmost_email",
        # Engineering / prototyping tools
        "create_and_run_script",
        "blender_run_script", "blender_create_project", "blender_export_stl",
        "blender_list_objects", "blender_open_file",
        "printer_status", "printer_upload", "printer_start",
        "printer_stop", "printer_list_files",
    ],
    "content": [
        "draft_content", "list_content_drafts", "update_content_draft",
        "get_content_calendar", "publish_content", "format_for_platform",
        "list_personas", "get_persona", "match_prospect_to_persona",
        "web_search", "web_fetch", "store_memory", "recall_memory",
    ],
    "hermes": None,
    "reasoner": [],
    "math": [],
}

# ── Security Monitor Configuration ──
SECURITY_MONITOR_CONFIG = {
    "monitor_agent": "security",
    "escalation_target": "user",
    "batch_interval_min": 90,
    "batch_interval_max": 180,
    "max_audit_queue_size": 500,
    "escalation_threshold": 0.7,
    "critical_threshold": 0.9,
}

# ── Security Heartbeat ──
SECURITY_HEARTBEAT_CONFIG = {
    "enabled": True,
    "interval_seconds": 600,
    "scan_processes": True,
    "scan_network": True,
    "scan_file_integrity": True,
    "watched_paths": [
        "/usr/local/bin",
        "~/Library/LaunchAgents",
        "~/Library/LaunchDaemons",
        "/Library/LaunchAgents",
        "/Library/LaunchDaemons",
    ],
    "baseline_path": str(STATE_DIR / "system_baseline.json"),
    "alert_on_new_process": True,
    "alert_on_new_connection": True,
    "alert_on_file_change": True,
}

# ── Scheduler ──
SCHEDULER_POLL_INTERVAL = 0.05
PARALLEL_SLOTS = 4
HERMES_IDLE_TTL = 300

# ── Planner Model ──
PLANNER_MODEL = "hermes"

# ── Channel Definitions ──
# Dynamic based on enabled agents
_base_channels = {
    "#general": {"hermes", "coder", "math", "classifier", "reasoner"},
    "#security": {"hermes", "security"},
    "#code": {"hermes", "coder", "claude"},
    "#ops": {"hermes", "classifier"},
    "#analysis": {"hermes", "reasoner", "math"},
}
if _profile.plugins.crm.enabled:
    _base_channels["#outreach"] = {"outreach", "reasoner", "coder"}
    _base_channels["#content"] = {"content", "outreach", "reasoner"}

# Filter to only include enabled agents
CHANNEL_DEFINITIONS = {}
enabled_set = set(AGENT_DEFINITIONS.keys())
for ch_name, ch_agents in _base_channels.items():
    filtered = ch_agents & enabled_set
    if filtered:
        CHANNEL_DEFINITIONS[ch_name] = filtered

# ── Cognitive Loop ──
COGNITIVE_LOOP_CONFIG = {
    "enabled": True,
    "cycle_interval_seconds": 120,
    "min_interval_seconds": 30,
    "urgent_threshold": 0.8,
    "moderate_threshold": 0.4,
    "reflection_every_n_cycles": 10,
    "morning_briefing_hour": 9,
    "evening_briefing_hour": 18,
    "auto_draft_content": _profile.plugins.crm.enabled,
    "auto_draft_outreach": _profile.plugins.crm.enabled,
    "watched_directories": [],
}
