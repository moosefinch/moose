"""Desktop action approval endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import verify_api_key
from models import ApprovalRequest
from tools_desktop import get_action_log, resolve_approval

router = APIRouter()


@router.post("/api/approve/{approval_id}", dependencies=[Depends(verify_api_key)])
async def approve_desktop_action(approval_id: str, req: ApprovalRequest, request: Request):
    success = resolve_approval(approval_id, req.approved)
    if not success:
        raise HTTPException(status_code=404, detail="Approval not found or expired")
    return {"status": "approved" if req.approved else "denied"}


@router.get("/api/desktop/log", dependencies=[Depends(verify_api_key)])
async def desktop_log(limit: int = 50):
    return {"actions": get_action_log(limit)}
