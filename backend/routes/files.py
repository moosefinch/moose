"""File upload and serving endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from auth import verify_api_key, get_core

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

router = APIRouter()


@router.post("/api/upload", dependencies=[Depends(verify_api_key)])
async def upload_file(file: UploadFile = File(...)):
    """Upload a file (streaming). Broadcasts file_ready via WebSocket."""
    core = get_core()
    safe_name = Path(file.filename).name
    if not safe_name or safe_name.startswith('.'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    save_path = UPLOADS_DIR / safe_name
    if not str(save_path.resolve()).startswith(str(UPLOADS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    total_size = 0
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                f.close()
                save_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_SIZE // (1024*1024)}MB limit")
            f.write(chunk)

    file_url = f"/api/files/{safe_name}"
    await core.broadcast({
        "type": "file_ready",
        "filename": safe_name,
        "url": file_url,
        "content_type": file.content_type or "",
    })
    return {"filename": safe_name, "url": file_url, "size": save_path.stat().st_size}


@router.get("/api/files/{filename}", dependencies=[Depends(verify_api_key)])
async def serve_file(filename: str):
    """Serve an uploaded file."""
    safe_name = Path(filename).name
    file_path = UPLOADS_DIR / safe_name
    if not str(file_path.resolve()).startswith(str(UPLOADS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
