"""Health, config, and API key rotation endpoints."""

import secrets
import time

from fastapi import APIRouter, Depends

from auth import verify_api_key, get_core, MOOSE_API_KEY
from db import db_connection
from tools import DB_PATH

router = APIRouter()


@router.get("/health")
def health():
    core = get_core()
    return {"status": "ok", "agent_ready": core._ready}


@router.get("/api/models", dependencies=[Depends(verify_api_key)])
async def api_models():
    return await get_core().get_status()


@router.post("/api/key/rotate", dependencies=[Depends(verify_api_key)])
async def rotate_api_key():
    """Generate a new API key. Old key remains valid for a 5-minute grace period."""
    import hashlib as _hl
    import auth as _auth
    from pathlib import Path

    now = time.time()
    grace_period = 300  # 5 minutes

    new_key = secrets.token_urlsafe(32)
    new_hash = _hl.sha256(new_key.encode()).hexdigest()
    old_hash = _hl.sha256(MOOSE_API_KEY.encode()).hexdigest()

    with db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (key_hash, created_at, expires_at, active) VALUES (?, ?, ?, 1)",
            (old_hash, now, now + grace_period))
        conn.execute(
            "INSERT INTO api_keys (key_hash, created_at, expires_at, active) VALUES (?, ?, NULL, 1)",
            (new_hash, now))
        conn.commit()

    # Update file and in-memory key
    key_path = Path(__file__).parent.parent / ".moose_api_key"
    key_path.write_text(new_key)
    key_path.chmod(0o600)
    _auth.MOOSE_API_KEY = new_key

    return {"new_key": new_key, "old_key_valid_until": now + grace_period}


@router.get("/api/config")
async def get_public_config():
    """Return system name, version, and enabled plugins. No auth required."""
    from profile import get_profile as _get_cfg_profile
    _cfg = _get_cfg_profile()
    enabled_plugins = []
    if _cfg.plugins.crm.enabled:
        enabled_plugins.append("crm")
    return {
        "system_name": _cfg.system.name,
        "version": "1.0.0",
        "enabled_plugins": enabled_plugins,
        "enabled_agents": _cfg.get_enabled_agents(),
    }
