"""Conversation CRUD endpoints."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key
from db import db_connection
from models import ConversationUpdate

router = APIRouter()


@router.get("/conversations", dependencies=[Depends(verify_api_key)])
def list_conversations():
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN conversation_messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """)
        return [dict(r) for r in c.fetchall()]


@router.post("/conversations", dependencies=[Depends(verify_api_key)])
def create_conversation():
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                  (conv_id, "New conversation", now, now))
        conn.commit()
    return {"id": conv_id, "title": "New conversation", "created_at": now, "updated_at": now}


@router.get("/conversations/{conv_id}", dependencies=[Depends(verify_api_key)])
def get_conversation(conv_id: str):
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        conv = c.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        c.execute("SELECT id, role, content, model_label, elapsed_seconds, tool_calls, plan, created_at FROM conversation_messages WHERE conversation_id = ? ORDER BY id ASC",
                  (conv_id,))
        messages = []
        for row in c.fetchall():
            msg = dict(row)
            if msg.get("tool_calls"):
                try:
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    msg["tool_calls"] = []
            if msg.get("plan"):
                try:
                    msg["plan"] = json.loads(msg["plan"])
                except (json.JSONDecodeError, TypeError):
                    msg["plan"] = None
            messages.append(msg)
        return {"conversation": dict(conv), "messages": messages}


@router.patch("/conversations/{conv_id}", dependencies=[Depends(verify_api_key)])
def update_conversation(conv_id: str, req: ConversationUpdate):
    now = datetime.now(timezone.utc).isoformat()
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                  (req.title, now, conv_id))
        conn.commit()
    return {"id": conv_id, "title": req.title, "updated_at": now}


@router.delete("/conversations/{conv_id}", dependencies=[Depends(verify_api_key)])
def delete_conversation(conv_id: str):
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conv_id,))
        c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()
    return {"status": "deleted", "id": conv_id}
