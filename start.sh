#!/bin/bash
set -e
# Development mode — runs backend + Vite dev server (hot reload).
# For production, use: scripts/install-daemon.sh
# The daemon serves the built frontend via FastAPI and survives terminal close.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# ── Dependency checks ──
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found in PATH" >&2
    exit 1
fi

if ! command -v node &>/dev/null && ! command -v npx &>/dev/null; then
    echo "Error: node/npx is required but not found in PATH" >&2
    exit 1
fi

# ── Activate venv if present ──
if [ -d "$BACKEND_DIR/.venv" ]; then
    source "$BACKEND_DIR/.venv/bin/activate"
fi

echo "=== Moose (Development Mode) ==="
echo ""

# Start backend
cd "$BACKEND_DIR"
echo "[1] Starting backend on http://127.0.0.1:8000"
python3 main.py &
BACKEND_PID=$!

# Wait for backend health check instead of fixed sleep
echo "    Waiting for backend..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "    Backend ready."
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Error: backend process exited unexpectedly" >&2
        exit 1
    fi
    sleep 1
done

# Start frontend (Vite dev server)
cd "$FRONTEND_DIR"
echo "[2] Starting frontend on http://127.0.0.1:3000"
npx vite --host 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo ""
echo "=== RUNNING ==="
echo "Backend:   http://127.0.0.1:8000"
echo "Frontend:  http://127.0.0.1:3000"
echo "API Docs:  http://127.0.0.1:8000/docs"
echo ""
echo "Press Ctrl+C to stop"

cleanup() {
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
}

trap cleanup EXIT

wait
