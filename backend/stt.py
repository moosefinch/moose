"""
Speech-to-text — lazy-loads faster-whisper for audio transcription.

Model configurable via MOOSE_WHISPER_MODEL env var (default: "base").
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_model = None
_model_size = os.environ.get("MOOSE_WHISPER_MODEL", "base")


def _get_model():
    """Lazy-load the faster-whisper model on first use."""
    global _model
    if _model is not None:
        return _model

    try:
        from faster_whisper import WhisperModel
        logger.info("Loading faster-whisper model: %s", _model_size)
        _model = WhisperModel(_model_size, device="auto", compute_type="auto")
        logger.info("faster-whisper model loaded: %s", _model_size)
        return _model
    except ImportError:
        logger.error("faster-whisper not installed. Install with: pip install faster-whisper>=1.0.0")
        raise RuntimeError("faster-whisper not installed")
    except Exception as e:
        logger.error("Failed to load faster-whisper model: %s", e)
        raise


def transcribe(audio_path: str, language: str = "en") -> str:
    """Transcribe an audio file to text using faster-whisper.

    Args:
        audio_path: Path to the audio file.
        language: Language code (default: "en").

    Returns:
        Transcribed text string.
    """
    model = _get_model()
    segments, info = model.transcribe(audio_path, language=language)
    text = " ".join(segment.text.strip() for segment in segments)
    logger.info("Transcribed %s (lang=%s, duration=%.1fs): %d chars",
                audio_path, info.language, info.duration, len(text))
    return text
