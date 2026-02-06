"""
OpenAI-compatible API endpoints for external integrations (e.g., OpenClaw).

Provides /v1/chat/completions and /v1/models so that any OpenAI-compatible
client can use Moose as a local inference provider.  Requests flow through
the existing classifier -> agent routing pipeline — nothing is bypassed.
"""

import json
import logging
import os
import secrets
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from auth import require_ready, get_core, MOOSE_API_KEY
from config import MODELS, MODEL_LABELS, TOKEN_LIMITS
from profile import get_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

# ── Configurable API key ──
# Falls back to the standard Moose key when MOOSE_OPENAI_API_KEY is unset.
OPENAI_COMPAT_API_KEY = os.environ.get("MOOSE_OPENAI_API_KEY", MOOSE_API_KEY)


# ── Auth dependency ──

def verify_openai_auth(request: Request):
    """Accept both Authorization: Bearer <key> and X-API-Key: <key>."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
    else:
        key = request.headers.get("x-api-key", "")

    if not key or not secrets.compare_digest(key, OPENAI_COMPAT_API_KEY):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid API key",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )


# ── Pydantic request models ──

class FunctionDef(BaseModel):
    name: str
    description: Optional[str] = ""
    parameters: Optional[dict] = None


class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef


class OAIChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "moose"
    messages: list[OAIChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[list[ToolDef]] = None
    tool_choice: Optional[str | dict] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    n: int = 1
    stop: Optional[str | list[str]] = None
    user: Optional[str] = None


# ── Helpers ──

def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _build_tool_context(tools: list[ToolDef]) -> str:
    """Produce a system-level prompt section describing the caller's tools."""
    lines = []
    for t in tools:
        fn = t.function
        sig = f"- {fn.name}: {fn.description or 'No description'}"
        if fn.parameters:
            sig += f"\n  Parameters: {json.dumps(fn.parameters)}"
        lines.append(sig)
    return (
        "\n\n[External tools available. To invoke one, include in your response "
        'a JSON block: {"tool_calls": [{"name": "<function>", "arguments": {<args>}}]}]\n'
        + "\n".join(lines)
    )


def _messages_to_moose(
    messages: list[OAIChatMessage],
    tools: list[ToolDef] | None = None,
) -> tuple[str, list | None]:
    """Convert an OpenAI messages array into (query, history) for core.chat().

    The last user-role message becomes the *query*; everything before it
    becomes *history* (list of {"role": ..., "content": ...} dicts).
    """
    tool_ctx = _build_tool_context(tools) if tools else ""
    system_patched = False
    processed: list[dict] = []

    for msg in messages:
        if msg.role == "system":
            content = msg.content or ""
            if tool_ctx and not system_patched:
                content += tool_ctx
                system_patched = True
            processed.append({"role": "system", "content": content})
        elif msg.role == "user":
            processed.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            processed.append({"role": "assistant", "content": msg.content or ""})
        elif msg.role == "tool":
            # Moose has no "tool" role — encode as user context.
            processed.append({
                "role": "user",
                "content": f"[Tool result for call {msg.tool_call_id}]: {msg.content or ''}",
            })

    # Inject tool context as a system message if none was present.
    if tool_ctx and not system_patched:
        processed.insert(0, {"role": "system", "content": tool_ctx.strip()})

    # Find the last user message — that's the query.
    query = ""
    split_idx = len(processed)
    for i in range(len(processed) - 1, -1, -1):
        if processed[i]["role"] == "user":
            query = processed[i]["content"]
            split_idx = i
            break

    history = processed[:split_idx] or None
    return query, history


def _parse_tool_calls(
    content: str,
    tools: list[ToolDef] | None,
) -> tuple[str | None, list | None]:
    """Extract structured tool calls from response text.

    Returns (cleaned_content, openai_tool_calls | None).
    """
    if not tools or not content:
        return content, None

    import re

    tool_names = {t.function.name for t in tools}
    patterns = [
        r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}',
        r'```json\s*(\{[^`]*"tool_calls"[^`]*\})\s*```',
        r'```\s*(\{[^`]*"tool_calls"[^`]*\})\s*```',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, content, re.DOTALL):
            raw = match.group(1) if match.lastindex else match.group(0)
            try:
                parsed = json.loads(raw)
                calls = parsed.get("tool_calls", [])
                if not isinstance(calls, list) or not calls:
                    continue
                oai_calls = []
                for call in calls:
                    name = call.get("name", "")
                    if name not in tool_names:
                        continue
                    oai_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(call.get("arguments", {})),
                        },
                    })
                if oai_calls:
                    cleaned = content.replace(match.group(0), "").strip()
                    return cleaned or None, oai_calls
            except (json.JSONDecodeError, AttributeError):
                continue

    return content, None


def _format_completion(
    completion_id: str,
    content: str | None,
    tool_calls: list | None,
    model: str,
    usage: dict,
) -> dict:
    """Build a non-streaming ChatCompletion response dict."""
    message: dict = {"role": "assistant"}
    if tool_calls:
        message["content"] = content
        message["tool_calls"] = tool_calls
        finish = "tool_calls"
    else:
        message["content"] = content or ""
        finish = "stop"

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish,
            }
        ],
        "usage": usage,
        "system_fingerprint": "fp_moose",
    }


def _openai_error(
    message: str,
    err_type: str = "server_error",
    status: int = 500,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "code": None}},
    )


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


# ── Endpoints ──

@router.post(
    "/chat/completions",
    dependencies=[Depends(verify_openai_auth), Depends(require_ready)],
)
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint."""
    core = get_core()

    if not req.messages:
        return _openai_error("messages array is required", "invalid_request_error", 400)

    query, history = _messages_to_moose(req.messages, req.tools)

    if not query:
        return _openai_error(
            "No user message found in messages array",
            "invalid_request_error",
            400,
        )

    cid = _completion_id()
    model_name = req.model or "moose"

    if req.stream:
        return StreamingResponse(
            _stream_response(core, query, history, req.tools, cid, model_name),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Non-streaming path ──
    try:
        result = await core.chat(query, history=history, use_tools=True)
    except Exception as e:
        logger.error("Chat pipeline error: %s", e)
        return _openai_error(str(e))

    if result.get("error"):
        return _openai_error(result.get("content", "Unknown error"))

    content = result.get("content", "")
    cleaned, tool_calls = _parse_tool_calls(content, req.tools)

    prompt_text = " ".join((m.content or "") for m in req.messages)
    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens(content)

    return _format_completion(
        completion_id=cid,
        content=cleaned,
        tool_calls=tool_calls,
        model=model_name,
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


async def _stream_response(core, query, history, tools, cid, model_name):
    """Async generator yielding OpenAI-format SSE chunks."""
    created = int(time.time())

    def _chunk(delta: dict, finish: str | None = None) -> str:
        obj = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish}
            ],
        }
        return f"data: {json.dumps(obj)}\n\n"

    # Role announcement
    yield _chunk({"role": "assistant"})

    # Run through the pipeline
    try:
        result = await core.chat(query, history=history, use_tools=True)
    except Exception as e:
        yield _chunk({"content": f"Error: {e}"}, "stop")
        yield "data: [DONE]\n\n"
        return

    content = result.get("content", "")
    cleaned, tool_calls = _parse_tool_calls(content, tools)

    if tool_calls:
        # Emit tool call deltas
        for idx, tc in enumerate(tool_calls):
            yield _chunk({
                "tool_calls": [{
                    "index": idx,
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }],
            })
        yield _chunk({}, "tool_calls")
    else:
        # Emit content in word-grouped chunks for progressive rendering.
        text = cleaned or ""
        if text:
            words = text.split(" ")
            buf = ""
            for word in words:
                buf = f"{buf} {word}" if buf else word
                if len(buf) >= 40:
                    yield _chunk({"content": buf})
                    buf = ""
            if buf:
                yield _chunk({"content": buf})
        yield _chunk({}, "stop")

    yield "data: [DONE]\n\n"


@router.get("/models", dependencies=[Depends(verify_openai_auth)])
async def list_models():
    """Return available models in OpenAI list format."""
    profile = get_profile()
    primary = profile.inference.models.primary

    data = [
        {
            "id": "moose",
            "object": "model",
            "created": 0,
            "owned_by": "moose",
            "permission": [],
            "root": "moose",
            "parent": None,
            "context_window": 131072,
            "max_tokens": primary.max_tokens or 4096,
        },
    ]

    # Expose the underlying model ID as an alias when configured.
    if primary.model_id:
        data.append({
            "id": primary.model_id,
            "object": "model",
            "created": 0,
            "owned_by": "moose",
            "permission": [],
            "root": primary.model_id,
            "parent": "moose",
            "context_window": 131072,
            "max_tokens": primary.max_tokens or 4096,
        })

    return {"object": "list", "data": data}
