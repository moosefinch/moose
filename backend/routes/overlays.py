"""Map overlay endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core
from models import OverlayRequest

router = APIRouter()


@router.post("/api/overlay", dependencies=[Depends(verify_api_key)])
async def create_overlay(req: OverlayRequest):
    core = get_core()
    overlay_id = str(uuid.uuid4())[:8]
    overlay_data = {
        "id": overlay_id,
        "overlay_type": req.overlay_type,
        "geojson": req.geojson,
        "style": req.style or {},
        "label": req.label or f"{req.overlay_type}_{overlay_id}",
    }
    core._overlays[overlay_id] = overlay_data
    await core.broadcast({"type": "overlay", "data": overlay_data})
    return overlay_data


@router.get("/api/overlays", dependencies=[Depends(verify_api_key)])
async def list_overlays():
    return list(get_core()._overlays.values())


@router.delete("/api/overlays/{overlay_id}", dependencies=[Depends(verify_api_key)])
async def delete_overlay(overlay_id: str):
    core = get_core()
    removed = core._overlays.pop(overlay_id, None)
    if not removed:
        raise HTTPException(status_code=404, detail="Overlay not found")
    await core.broadcast({"type": "clear_overlay", "id": overlay_id})
    return {"status": "removed", "id": overlay_id}
