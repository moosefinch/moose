"""Agent communication channel endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core, sanitize_input
from db import db_connection
from models import ChannelPostRequest

router = APIRouter()


@router.get("/api/channels", dependencies=[Depends(verify_api_key)])
async def list_channels():
    """List all channels with message counts."""
    core = get_core()
    if not hasattr(core, 'channel_manager') or not core.channel_manager:
        return []
    return core.channel_manager.get_all_channels()


@router.get("/api/channels/{name:path}", dependencies=[Depends(verify_api_key)])
async def get_channel_messages(name: str, limit: int = 50):
    """Get messages for a channel."""
    core = get_core()
    if not hasattr(core, 'channel_manager') or not core.channel_manager:
        return []
    if not name.startswith("#"):
        name = f"#{name}"
    return core.channel_manager.get_channel_messages(name, limit=limit)


@router.post("/api/channels/post", dependencies=[Depends(verify_api_key)])
async def post_to_channel(req: ChannelPostRequest):
    """Post a message to a channel as the operator."""
    core = get_core()
    channel = req.channel if req.channel.startswith("#") else f"#{req.channel}"
    content = sanitize_input(req.content, 5000)
    sender = sanitize_input(req.sender or "operator", 100)
    if not content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO channel_messages (id, channel, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (msg_id, channel, sender, content, now))
        conn.commit()

    msg_data = {
        "type": "channel_message",
        "id": msg_id,
        "channel": channel,
        "sender": sender,
        "content": content,
        "timestamp": now,
    }
    await core.broadcast(msg_data)
    return {"id": msg_id, "channel": channel, "sender": req.sender, "timestamp": now}
