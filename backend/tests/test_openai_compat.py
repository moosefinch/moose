#!/usr/bin/env python3
"""
Integration tests for the OpenAI-compatible API endpoints.

Run against a live Moose instance:

    python tests/test_openai_compat.py                        # defaults
    MOOSE_HOST=192.168.1.50 python tests/test_openai_compat.py  # custom host

The script reads the API key from MOOSE_API_KEY env var or
backend/.moose_api_key automatically.
"""

import json
import os
import sys
from pathlib import Path

import httpx

# ── Configuration ──

HOST = os.environ.get("MOOSE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOOSE_PORT", "8000"))
BASE = f"http://{HOST}:{PORT}/v1"


def _load_api_key() -> str:
    key = os.environ.get("MOOSE_OPENAI_API_KEY") or os.environ.get("MOOSE_API_KEY")
    if key:
        return key
    key_file = Path(__file__).parent.parent / ".moose_api_key"
    if key_file.exists():
        return key_file.read_text().strip()
    print("ERROR: No API key found. Set MOOSE_API_KEY or create backend/.moose_api_key")
    sys.exit(1)


API_KEY = _load_api_key()
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

passed = 0
failed = 0


def report(name: str, ok: bool, detail: str = ""):
    global passed, failed
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        passed += 1
    else:
        failed += 1


# ── 1. GET /v1/models ──

def test_models():
    print("\n=== GET /v1/models ===")
    r = httpx.get(f"{BASE}/models", headers=HEADERS, timeout=10)
    report("status 200", r.status_code == 200, f"got {r.status_code}")

    body = r.json()
    report("object == list", body.get("object") == "list")
    report("data is list", isinstance(body.get("data"), list))
    report("at least one model", len(body.get("data", [])) >= 1)

    if body.get("data"):
        m = body["data"][0]
        report("model has id", "id" in m)
        report("model has object", m.get("object") == "model")
        report("model has context_window", "context_window" in m)
        report("model has max_tokens", "max_tokens" in m)
        print(f"  Models returned: {[d['id'] for d in body['data']]}")


# ── 2. POST /v1/chat/completions (non-streaming) ──

def test_chat_non_streaming():
    print("\n=== POST /v1/chat/completions (non-streaming) ===")
    payload = {
        "model": "moose",
        "messages": [
            {"role": "user", "content": "Say exactly: hello world"}
        ],
        "stream": False,
    }
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, json=payload, timeout=120)
    report("status 200", r.status_code == 200, f"got {r.status_code}")

    body = r.json()
    report("object == chat.completion", body.get("object") == "chat.completion")
    report("has id (chatcmpl-*)", body.get("id", "").startswith("chatcmpl-"))
    report("has model field", "model" in body)
    report("has usage", "usage" in body)

    choices = body.get("choices", [])
    report("one choice", len(choices) == 1)

    if choices:
        c = choices[0]
        report("finish_reason is stop", c.get("finish_reason") == "stop")
        msg = c.get("message", {})
        report("role == assistant", msg.get("role") == "assistant")
        report("content is non-empty string", isinstance(msg.get("content"), str) and len(msg["content"]) > 0)
        print(f"  Response preview: {msg.get('content', '')[:120]}")

    usage = body.get("usage", {})
    report("usage has prompt_tokens", "prompt_tokens" in usage)
    report("usage has completion_tokens", "completion_tokens" in usage)
    report("usage has total_tokens", "total_tokens" in usage)


# ── 3. POST /v1/chat/completions (streaming) ──

def test_chat_streaming():
    print("\n=== POST /v1/chat/completions (streaming) ===")
    payload = {
        "model": "moose",
        "messages": [
            {"role": "user", "content": "Say exactly: streaming test"}
        ],
        "stream": True,
    }
    chunks = []
    full_content = ""
    got_done = False
    got_role = False
    got_finish = False

    with httpx.stream(
        "POST", f"{BASE}/chat/completions",
        headers=HEADERS, json=payload, timeout=120,
    ) as r:
        report("status 200", r.status_code == 200, f"got {r.status_code}")
        for line in r.iter_lines():
            if not line:
                continue
            if line == "data: [DONE]":
                got_done = True
                continue
            if line.startswith("data: "):
                data = json.loads(line[6:])
                chunks.append(data)
                delta = data.get("choices", [{}])[0].get("delta", {})
                if "role" in delta:
                    got_role = True
                if "content" in delta:
                    full_content += delta["content"]
                finish = data.get("choices", [{}])[0].get("finish_reason")
                if finish:
                    got_finish = True

    report("received [DONE]", got_done)
    report("got role delta", got_role)
    report("got finish_reason", got_finish)
    report("received >= 2 chunks", len(chunks) >= 2, f"got {len(chunks)}")
    report("all chunks have id", all("id" in c for c in chunks))
    report("all chunks are chat.completion.chunk",
           all(c.get("object") == "chat.completion.chunk" for c in chunks))
    report("assembled content non-empty", len(full_content) > 0)
    print(f"  Chunks: {len(chunks)}  Content preview: {full_content[:120]}")


# ── 4. POST /v1/chat/completions (tool use) ──

def test_chat_tool_use():
    print("\n=== POST /v1/chat/completions (tool use) ===")
    payload = {
        "model": "moose",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. When asked about the weather, always call the get_weather tool."},
            {"role": "user", "content": "What's the weather in London?"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"},
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "stream": False,
    }
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, json=payload, timeout=120)
    report("status 200", r.status_code == 200, f"got {r.status_code}")

    body = r.json()
    report("valid completion object", body.get("object") == "chat.completion")

    choices = body.get("choices", [])
    if not choices:
        report("has choices", False)
        return

    msg = choices[0].get("message", {})
    tc = msg.get("tool_calls")

    # The model may or may not produce a tool call — both are valid responses.
    # We validate structure if tool_calls are present.
    if tc:
        report("tool_calls is list", isinstance(tc, list))
        report("at least one tool call", len(tc) >= 1)
        if tc:
            call = tc[0]
            report("call has id", "id" in call)
            report("call type == function", call.get("type") == "function")
            fn = call.get("function", {})
            report("function has name", "name" in fn)
            report("function has arguments (str)", isinstance(fn.get("arguments"), str))
            report("finish_reason == tool_calls", choices[0].get("finish_reason") == "tool_calls")
            print(f"  Tool call: {fn.get('name')}({fn.get('arguments', '')})")
    else:
        # Model responded with text instead — still a valid response.
        report("text response (no tool call)", isinstance(msg.get("content"), str))
        print(f"  Note: Model returned text instead of tool call — "
              f"this is acceptable (model discretion).")
        print(f"  Response: {msg.get('content', '')[:120]}")


# ── 5. Auth rejection test ──

def test_auth_rejection():
    print("\n=== Auth rejection ===")
    bad_headers = {"Authorization": "Bearer invalid-key", "Content-Type": "application/json"}
    r = httpx.get(f"{BASE}/models", headers=bad_headers, timeout=10)
    report("rejected with 401", r.status_code == 401)
    body = r.json()
    report("error body has 'error' key", "error" in body.get("detail", {}))


# ── 6. Validation error test ──

def test_validation_error():
    print("\n=== Validation: empty messages ===")
    payload = {"model": "moose", "messages": []}
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, json=payload, timeout=10)
    report("returns 400", r.status_code == 400, f"got {r.status_code}")


# ── Run ──

if __name__ == "__main__":
    print(f"Moose OpenAI-compat integration tests")
    print(f"Target: {BASE}")
    print(f"API key: ****...{API_KEY[-4:]}")

    test_models()
    test_auth_rejection()
    test_validation_error()
    test_chat_non_streaming()
    test_chat_streaming()
    test_chat_tool_use()

    print(f"\n{'=' * 40}")
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    sys.exit(1 if failed else 0)
