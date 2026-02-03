#!/bin/bash
set -e

echo "=== GPS Daemon Uninstaller ==="
echo ""

PLIST_DST="$HOME/Library/LaunchAgents/com.gps.backend.plist"

if launchctl list 2>/dev/null | grep -q "com.gps.backend"; then
    echo "Stopping com.gps.backend service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "Service stopped."
fi
if [ -f "$PLIST_DST" ]; then
    rm "$PLIST_DST"
    echo "Removed $PLIST_DST"
fi

# Check PID file
pid_dir="$HOME/.gps"
pid_file="$pid_dir/gps.pid"
if [ -f "$pid_file" ]; then
    PID=$(cat "$pid_file")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Killing remaining process (PID $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    rm "$pid_file"
fi

echo ""
echo "GPS daemon uninstalled."
echo "State files preserved in backend/memory/ (state.json, SOUL.md)."
echo "Logs preserved in ~/Library/Logs/gps-backend*.log."
echo ""
echo "To run in development mode, use start.sh instead."
