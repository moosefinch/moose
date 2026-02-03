"""
Moose Daemon — Persistent background process managed by launchd.

Responsibilities:
  - Start TTS server as subprocess (port 8787), health-check it
  - Start FastAPI via uvicorn programmatically
  - Signal handling (SIGTERM -> graceful shutdown)
  - Write PID file to ~/.moose/moose.pid
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Ensure backend directory is on the path
BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(BACKEND_DIR))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("moose.daemon")

PID_DIR = Path.home() / ".moose"
PID_FILE = PID_DIR / "moose.pid"
TTS_VENV_PYTHON = BACKEND_DIR / ".venv-tts" / "bin" / "python"
TTS_SERVER_SCRIPT = BACKEND_DIR / "tts_server.py"
TTS_PORT = 8787
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000


def write_pid():
    """Write current PID to ~/.moose/moose.pid."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    logger.info("PID %d written to %s", os.getpid(), PID_FILE)


def remove_pid():
    """Remove PID file."""
    PID_FILE.unlink(missing_ok=True)


def start_tts_server() -> subprocess.Popen | None:
    """Start the Kokoro TTS server as a subprocess."""
    if not TTS_VENV_PYTHON.exists():
        logger.warning("TTS venv not found at %s — skipping TTS", TTS_VENV_PYTHON)
        return None

    logger.info("Starting TTS server...")
    proc = subprocess.Popen(
        [str(TTS_VENV_PYTHON), str(TTS_SERVER_SCRIPT)],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Health-check TTS server (up to 30s)
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{TTS_PORT}/health", timeout=2)
            logger.info("TTS server ready")
            return proc
        except Exception:
            time.sleep(1)

    logger.warning("TTS server did not start within 30s — continuing without TTS")
    return proc


def run():
    """Main daemon entry point."""
    write_pid()

    tts_proc = start_tts_server()
    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("Received signal %s — initiating graceful shutdown", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    async def serve():
        """Run uvicorn programmatically with graceful shutdown support."""
        import uvicorn

        config = uvicorn.Config(
            "main:app",
            host=BACKEND_HOST,
            port=BACKEND_PORT,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # Run server in a background task
        server_task = asyncio.create_task(server.serve())

        # Wait for shutdown signal
        await shutdown_event.wait()
        logger.info("Shutdown signal received — stopping uvicorn")

        server.should_exit = True
        await server_task

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up TTS process
        if tts_proc and tts_proc.poll() is None:
            logger.info("Stopping TTS server...")
            tts_proc.terminate()
            try:
                tts_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tts_proc.kill()

        remove_pid()
        logger.info("Moose daemon stopped")


if __name__ == "__main__":
    run()
