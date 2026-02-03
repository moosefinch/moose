"""
Printer REST routes — wraps existing printer plugin tools.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from auth import verify_api_key, require_ready

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/printer",
    tags=["printer"],
    dependencies=[Depends(verify_api_key), Depends(require_ready)],
)


class PrintStartRequest(BaseModel):
    file_name: str


@router.get("/status")
async def get_printer_status(request: Request):
    """Get current printer status via plugin tools."""
    core = request.app.state.agent_core
    try:
        result = await core.execute_tool("printer_status", {})
        if isinstance(result, dict):
            return result
        return {"state": "unknown", "connected": False}
    except Exception as e:
        logger.warning("Printer status failed: %s", e)
        return {"state": "offline", "connected": False}


@router.get("/files")
async def get_printer_files(request: Request):
    """List files on printer."""
    core = request.app.state.agent_core
    try:
        result = await core.execute_tool("printer_list_files", {})
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "files" in result:
            return result["files"]
        return []
    except Exception as e:
        logger.warning("Printer list files failed: %s", e)
        return []


@router.post("/upload")
async def upload_to_printer(request: Request, file: UploadFile = File(...)):
    """Upload a G-code file to the printer."""
    core = request.app.state.agent_core
    try:
        content = await file.read()
        result = await core.execute_tool("printer_upload", {
            "filename": file.filename,
            "content": content,
        })
        return {"success": True, "filename": file.filename, "result": result}
    except Exception as e:
        logger.error("Printer upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_print(request: Request, body: PrintStartRequest):
    """Start printing a file."""
    core = request.app.state.agent_core
    try:
        result = await core.execute_tool("printer_start", {"file_name": body.file_name})
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Printer start failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_print(request: Request):
    """Stop the current print."""
    core = request.app.state.agent_core
    try:
        result = await core.execute_tool("printer_stop", {})
        return {"success": True, "result": result}
    except Exception as e:
        logger.error("Printer stop failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
