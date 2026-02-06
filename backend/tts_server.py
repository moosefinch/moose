"""
Kokoro TTS Server — standalone microservice for Moose voice output.

Runs in its own Python 3.11 venv with mlx-audio.
Moose backend proxies requests here for speech generation.

Usage:
    .venv-tts/bin/python tts_server.py [--port 8787]

Endpoints:
    POST /generate  — generate speech from text, returns .wav file
        Body: {"text": "...", "voice": "bm_lewis" (optional)}
    GET  /health    — check if server and model are ready
"""

import argparse
import io
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tts_server")

import mlx.core as mx
from mlx_audio.tts import load as load_tts_model
from mlx_audio.audio_io import write as audio_write

# ── Globals ──
_model = None
_model_lock = threading.Lock()
MODEL_ID = "mlx-community/Kokoro-82M-bf16"
DEFAULT_VOICE = "bm_lewis"
DEFAULT_LANG = "b"


def load_model():
    """Load Kokoro via mlx-audio."""
    global _model

    logger.info("Loading %s ...", MODEL_ID)
    _model = load_tts_model(MODEL_ID, lazy=False)
    logger.info("Model loaded (sample rate: %s)", _model.sample_rate)


class TTSHandler(BaseHTTPRequestHandler):
    """HTTP request handler for TTS generation."""

    def do_POST(self):
        if self.path == "/generate":
            self._handle_generate()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == "/health":
            self._handle_health()
        else:
            self.send_error(404)

    def _handle_generate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        text = data.get("text", "").strip()
        if not text:
            self.send_error(400, "Missing 'text' field")
            return

        voice = data.get("voice", DEFAULT_VOICE)

        buf = io.BytesIO()

        with _model_lock:
            try:
                generated = False
                for result in _model.generate(
                    text=text,
                    voice=voice,
                    lang_code=DEFAULT_LANG,
                    verbose=False,
                ):
                    audio_write(buf, result.audio, result.sample_rate, format="wav")
                    generated = True
                    break

                if not generated:
                    self.send_error(500, "Generation produced no output")
                    return
            except Exception as e:
                logger.error("Generation error: %s", e)
                self.send_error(500, f"Generation failed: {e}")
                return

        wav_data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(wav_data)

    def _handle_health(self):
        status = {
            "ready": _model is not None,
            "model": MODEL_ID,
            "voice": DEFAULT_VOICE,
            "engine": "mlx-audio/kokoro",
        }
        body = json.dumps(status).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if args and "200" not in str(args[0]):
            logger.info("%s", args[0])


def main():
    global DEFAULT_VOICE

    parser = argparse.ArgumentParser(description="Kokoro TTS Server for Moose")
    parser.add_argument("--port", type=int, default=8787, help="Port to listen on")
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE,
                        help="Default voice (e.g. bm_lewis, bm_george, bm_daniel)")
    args = parser.parse_args()

    DEFAULT_VOICE = args.voice

    load_model()

    server = HTTPServer(("127.0.0.1", args.port), TTSHandler)
    logger.info("Listening on http://127.0.0.1:%d", args.port)
    logger.info("Voice: %s", DEFAULT_VOICE)
    logger.info("POST /generate  — generate speech")
    logger.info("GET  /health    — health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
