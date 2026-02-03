#!/bin/bash
set -e

echo "=== GPS Daemon Installer ==="
echo ""

# Detect INSTALL_DIR from this script's location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

USER_HOME="$HOME"
LOG_DIR="$USER_HOME/Library/Logs/gps"

PLIST_TEMPLATE="$INSTALL_DIR/com.gps.backend.plist.template"
PLIST_DST="$USER_HOME/Library/LaunchAgents/com.gps.backend.plist"
FRONTEND_DIR="$INSTALL_DIR/frontend"

if [ ! -f "$PLIST_TEMPLATE" ]; then
    echo "ERROR: Template not found at $PLIST_TEMPLATE"
    exit 1
fi

# 1. Build frontend
echo "[1/5] Building frontend..."
cd "$FRONTEND_DIR"
npm install --silent
npm run build
echo "      Frontend built to $FRONTEND_DIR/dist"

# 2. Ensure directories exist
echo "[2/5] Setting up directories..."
mkdir -p "$LOG_DIR"
mkdir -p "$USER_HOME/Library/LaunchAgents"
mkdir -p "$INSTALL_DIR/backend/memory"

# 3. Generate plist from template
echo "[3/5] Generating plist from template..."
sed \
    -e "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
    -e "s|{{USER_HOME}}|$USER_HOME|g" \
    -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DST"
echo "      Plist written to $PLIST_DST"

# 4. Stop existing service if running, then load
echo "[4/5] Installing launchd service..."
if launchctl list 2>/dev/null | grep -q "com.gps.backend"; then
    echo "      Stopping existing GPS service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi
launchctl load "$PLIST_DST"

# 5. Verify
echo "[5/5] Verifying..."
sleep 3

if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo ""
    echo "=== GPS daemon is running ==="
    echo "Backend:  http://127.0.0.1:8000"
    echo "Health:   http://127.0.0.1:8000/health"
    echo "Logs:     $LOG_DIR/gps-backend.log"
    echo "Errors:   $LOG_DIR/gps-backend-error.log"
    echo ""
    echo "GPS will survive terminal close and auto-start on reboot."
else
    echo ""
    echo "WARNING: GPS may still be starting. Check logs:"
    echo "  tail -f $LOG_DIR/gps-backend.log"
    echo "  tail -f $LOG_DIR/gps-backend-error.log"
fi
