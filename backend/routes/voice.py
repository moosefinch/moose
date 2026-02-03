"""Voice input endpoints — speech-to-text transcription."""

import os
import tempfile
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/voice/transcribe", dependencies=[Depends(verify_api_key)])
async def transcribe_audio(file: UploadFile = File(...)):
    """Accept multipart audio upload, transcribe via faster-whisper, return text."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save to temp file
    suffix = os.path.splitext(file.filename)[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        from stt import transcribe
        text = transcribe(tmp.name)
        return {"text": text}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Transcription failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
