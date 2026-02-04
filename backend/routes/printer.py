"""
Printer REST routes — wraps existing printer plugin tools.
"""

import json
import logging
import tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from auth import verify_api_key, require_ready

from plugins.printing.tools import (
    printer_status,
    printer_upload,
    printer_start,
    printer_stop,
    printer_list_files,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/printer",
    tags=["printer"],
    dependencies=[Depends(verify_api_key), Depends(require_ready)],
)


class PrintStartRequest(BaseModel):
    file_name: str


@router.get("/status")
async def get_printer_status():
    """Get current printer status via plugin tools."""
    try:
        result = printer_status()
        if result.startswith("Error:"):
            return {"state": "offline", "connected": False, "error": result}
        data = json.loads(result)
        return data
    except json.JSONDecodeError:
        return {"state": "unknown", "connected": False, "raw": result}
    except Exception as e:
        logger.warning("Printer status failed: %s", e)
        return {"state": "offline", "connected": False}


@router.get("/files")
async def get_printer_files():
    """List files on printer."""
    try:
        result = printer_list_files()
        if result.startswith("Error:") or result.startswith("FTPS error:"):
            return {"files": [], "error": result}
        # Parse the text output
        lines = result.split("\n")
        files = [line.strip() for line in lines[1:] if line.strip()]
        return {"files": files}
    except Exception as e:
        logger.warning("Printer list files failed: %s", e)
        return {"files": [], "error": str(e)}


@router.post("/upload")
async def upload_to_printer(file: UploadFile = File(...)):
    """Upload a G-code or 3mf file to the printer."""
    try:
        # Save uploaded file to temp location
        content = await file.read()
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = printer_upload(tmp_path)

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if result.startswith("Error:") or result.startswith("FTPS"):
            raise HTTPException(status_code=500, detail=result)

        return {"success": True, "filename": file.filename, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Printer upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_print(body: PrintStartRequest):
    """Start printing a file."""
    try:
        result = printer_start(body.file_name)
        if result.startswith("Error:"):
            raise HTTPException(status_code=500, detail=result)
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Printer start failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_print():
    """Stop the current print."""
    try:
        result = printer_stop()
        if result.startswith("Error:"):
            raise HTTPException(status_code=500, detail=result)
        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Printer stop failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
