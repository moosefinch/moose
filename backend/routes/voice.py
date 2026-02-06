"""Voice endpoints — speech-to-text transcription and text-to-speech synthesis."""

import os
import tempfile
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter()

TTS_SERVER_URL = "http://127.0.0.1:8787"


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "bm_lewis"


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


@router.post("/api/voice/synthesize", dependencies=[Depends(verify_api_key)])
async def synthesize_speech(req: SynthesizeRequest):
    """Proxy text to Kokoro TTS server and return WAV audio."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{TTS_SERVER_URL}/generate",
                json={"text": req.text, "voice": req.voice},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="TTS generation failed")
        return Response(content=resp.content, media_type="audio/wav")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="TTS server not available")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS generation timed out")
