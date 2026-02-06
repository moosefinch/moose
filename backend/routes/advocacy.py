"""Advocacy system API routes — goals, patterns, onboarding."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core
from models import GoalCreate, GoalUpdate, EvidenceCreate, OnboardingResponse
from advocacy.models import Evidence

router = APIRouter()


def _get_advocacy():
    """Return the advocacy system or raise 503 if disabled."""
    core = get_core()
    if core.advocacy_system is None:
        raise HTTPException(status_code=503, detail="Advocacy system is not enabled")
    return core


# ── Status ──

@router.get("/api/advocacy/status", dependencies=[Depends(verify_api_key)])
async def advocacy_status():
    core = _get_advocacy()
    return core.advocacy_system.get_status()


# ── Goals ──

@router.get("/api/advocacy/goals", dependencies=[Depends(verify_api_key)])
async def list_goals():
    core = _get_advocacy()
    goals = core.advocacy_system.goals
    active = [g.to_dict() for g in goals.get_active_goals()]
    unconfirmed = [g.to_dict() for g in goals.get_unconfirmed_goals()]
    return {"active": active, "unconfirmed": unconfirmed}


@router.post("/api/advocacy/goals", dependencies=[Depends(verify_api_key)])
async def create_goal(body: GoalCreate):
    core = _get_advocacy()
    goal = core.advocacy_system.goals.add_goal(
        text=body.text,
        category=body.category,
        priority=body.priority,
        parent_id=body.parent_id,
    )
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "goal_created"}))
    return goal.to_dict()


@router.patch("/api/advocacy/goals/{goal_id}", dependencies=[Depends(verify_api_key)])
async def update_goal(goal_id: str, body: GoalUpdate):
    core = _get_advocacy()
    goals = core.advocacy_system.goals
    if goals.get_goal(goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    if body.status is not None:
        goals.update_status(goal_id, body.status)
    if body.priority is not None:
        goals.update_priority(goal_id, body.priority)
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "goal_updated"}))
    return goals.get_goal(goal_id).to_dict()


@router.post("/api/advocacy/goals/{goal_id}/confirm", dependencies=[Depends(verify_api_key)])
async def confirm_goal(goal_id: str):
    core = _get_advocacy()
    ok = core.advocacy_system.goals.confirm_goal(goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found or already confirmed")
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "goal_confirmed"}))
    return {"ok": True}


@router.post("/api/advocacy/goals/{goal_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_goal(goal_id: str):
    core = _get_advocacy()
    ok = core.advocacy_system.goals.reject_goal(goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found or already rejected")
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "goal_rejected"}))
    return {"ok": True}


@router.post("/api/advocacy/goals/{goal_id}/evidence", dependencies=[Depends(verify_api_key)])
async def record_evidence(goal_id: str, body: EvidenceCreate):
    core = _get_advocacy()
    goals = core.advocacy_system.goals
    if goals.get_goal(goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    evidence = Evidence(type=body.type, description=body.description)
    goals.record_evidence(goal_id, evidence)
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "evidence_recorded"}))
    return {"ok": True}


# ── Patterns ──

@router.get("/api/advocacy/patterns", dependencies=[Depends(verify_api_key)])
async def list_patterns():
    core = _get_advocacy()
    patterns = core.advocacy_system.watchdog.get_active_patterns()
    return [p.to_dict() for p in patterns]


@router.post("/api/advocacy/patterns/{pattern_id}/dismiss", dependencies=[Depends(verify_api_key)])
async def dismiss_pattern(pattern_id: str):
    core = _get_advocacy()
    pattern = core.advocacy_system.watchdog.get_pattern(pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    core.advocacy_system.friction.dismiss(pattern)
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "pattern_dismissed"}))
    return {"ok": True}


# ── Onboarding ──

@router.get("/api/advocacy/onboarding", dependencies=[Depends(verify_api_key)])
async def onboarding_status():
    core = _get_advocacy()
    ob = core.advocacy_system.onboarding
    status = ob.get_status()
    prompt = ob.get_current_prompt() if not ob.is_complete else None
    return {**status, "current_prompt": prompt}


@router.post("/api/advocacy/onboarding/start", dependencies=[Depends(verify_api_key)])
async def start_onboarding():
    core = _get_advocacy()
    prompt = core.advocacy_system.onboarding.start()
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "onboarding_started"}))
    return {"prompt": prompt}


@router.post("/api/advocacy/onboarding/respond", dependencies=[Depends(verify_api_key)])
async def respond_onboarding(body: OnboardingResponse):
    core = _get_advocacy()
    result = core.advocacy_system.onboarding.process_response(body.text)
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "onboarding_response"}))
    return result


@router.post("/api/advocacy/onboarding/reset", dependencies=[Depends(verify_api_key)])
async def reset_onboarding():
    core = _get_advocacy()
    core.advocacy_system.onboarding.reset()
    asyncio.create_task(core.broadcast({"type": "advocacy_update", "subtype": "onboarding_reset"}))
    return {"ok": True}
