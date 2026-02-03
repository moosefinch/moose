"""Chat query and WebSocket endpoints."""

import asyncio
import json
import logging
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone

from auth import verify_api_key, require_ready, get_core, MOOSE_API_KEY
from db import db_connection
from models import ChatQuery

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    from profile import get_profile as _get_profile
    _ws_profile = _get_profile()
    origin = websocket.headers.get("origin", "")
    allowed_origins = _ws_profile.web.cors_origins
    if origin and origin not in allowed_origins:
        await websocket.close(code=4003, reason="Origin not allowed")
        return
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        auth_msg = json.loads(raw)
        if (
            not isinstance(auth_msg, dict)
            or auth_msg.get("type") != "auth"
            or not isinstance(auth_msg.get("api_key"), str)
            or not secrets.compare_digest(auth_msg["api_key"], MOOSE_API_KEY)
        ):
            await websocket.close(code=4001, reason="Invalid or missing API key")
            return
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
        await websocket.close(code=4001, reason="Invalid or missing API key")
        return
    core = get_core()
    core.ws_clients.append(websocket)
    _WS_MAX_MESSAGE_SIZE = 50_000
    _WS_MAX_QUERY_LENGTH = 10_000
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif len(data) > _WS_MAX_MESSAGE_SIZE:
                await websocket.send_json({"type": "error", "message": "Message too large"})
            else:
                try:
                    msg = json.loads(data)
                    if not isinstance(msg, dict):
                        await websocket.send_json({"type": "error", "message": "Invalid message format"})
                        continue
                    msg_type = msg.get("type")
                    if msg_type == "query":
                        query_text = str(msg.get("query", ""))[:_WS_MAX_QUERY_LENGTH]
                        if not query_text.strip():
                            await websocket.send_json({"type": "error", "message": "Empty query"})
                            continue
                        conv_id = msg.get("conversation_id")
                        if conv_id and (not isinstance(conv_id, str) or len(conv_id) > 100):
                            await websocket.send_json({"type": "error", "message": "Invalid conversation_id"})
                            continue
                        history = msg.get("history")

                        if conv_id:
                            with db_connection() as conn:
                                c = conn.cursor()
                                c.execute("SELECT role, content FROM conversation_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 50", (conv_id,))
                                rows = c.fetchall()
                                if rows:
                                    history = [{"role": r[0], "content": r[1]} for r in reversed(rows)]

                        result = await core.chat(
                            query_text,
                            history=history,
                            use_tools=msg.get("use_tools", True),
                            stream=True,
                        )
                        await websocket.send_json({"type": "response", "data": result, "conversation_id": conv_id})
                    else:
                        await websocket.send_json({"type": "error", "message": f"Unknown message type: {str(msg_type)[:50]}"})
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                except Exception as e:
                    logger.warning(
                        "[WS] Error processing message: %s: %s", type(e).__name__, str(e)[:200]
                    )
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in core.ws_clients:
            core.ws_clients.remove(websocket)


@router.post("/api/query", dependencies=[Depends(verify_api_key), Depends(require_ready)])
async def api_query(req: ChatQuery):
    core = get_core()

    if req.conversation_id:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT role, content FROM conversation_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 50",
                      (req.conversation_id,))
            rows = c.fetchall()
            history = [{"role": r[0], "content": r[1]} for r in reversed(rows)] if rows else None

        now = datetime.now(timezone.utc).isoformat()
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO conversation_messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                      (req.conversation_id, "user", req.query, now))
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, req.conversation_id))
            conn.commit()
    else:
        history = [{"role": m.role, "content": m.content} for m in req.history] if req.history else None

    if req.stream:
        async def event_stream():
            yield f"data: {json.dumps({'type': 'start', 'message': 'Processing...'})}\n\n"
            result = await core.chat(req.query, history=history, use_tools=req.use_tools, stream=True)
            yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    result = await core.chat(req.query, history=history, use_tools=req.use_tools)

    if req.conversation_id:
        now = datetime.now(timezone.utc).isoformat()
        with db_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO conversation_messages (conversation_id, role, content, model_label, elapsed_seconds, tool_calls, plan, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (req.conversation_id, "assistant", result.get("content", ""),
                 result.get("model_label", ""), result.get("elapsed_seconds"),
                 json.dumps(result.get("tool_calls", [])),
                 json.dumps(result.get("plan")),
                 now))
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, req.conversation_id))

            c.execute("SELECT title FROM conversations WHERE id = ?", (req.conversation_id,))
            row = c.fetchone()
            if row and (not row[0] or row[0] == "New conversation"):
                auto_title = req.query[:50].strip()
                if len(req.query) > 50:
                    auto_title += "..."
                c.execute("UPDATE conversations SET title = ? WHERE id = ?", (auto_title, req.conversation_id))

            conn.commit()

        if core.memory._api_base:
            try:
                embed_text = f"User: {req.query}\nAssistant:{result.get('content', '')[:500]}"
                await core.memory.store(embed_text, tags=f"conversation,{req.conversation_id}")
            except Exception as e:
                logger.debug("Memory storage failed: %s", e)

    return result
