"""Agent system visibility and mission endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core

router = APIRouter()


@router.get("/api/agents", dependencies=[Depends(verify_api_key)])
async def list_agents():
    """List all agents with their current state."""
    core = get_core()
    if not hasattr(core, 'registry') or not core.registry:
        return []
    agents = []
    for agent in core.registry.all():
        pending_count = core.bus.get_pending(agent.agent_id) if hasattr(core, 'bus') else []
        agents.append({
            "id": agent.agent_id,
            "model_key": agent.model_key,
            "model_size": agent.model_size.value,
            "state": agent.state.value,
            "can_use_tools": agent.can_use_tools,
            "capabilities": agent.definition.capabilities,
            "pending_messages": len(pending_count) if isinstance(pending_count, list) else 0,
        })
    return agents


@router.get("/api/agents/{agent_id}", dependencies=[Depends(verify_api_key)])
async def get_agent(agent_id: str):
    """Get detailed agent info."""
    core = get_core()
    if not hasattr(core, 'registry') or not core.registry:
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    agent = core.registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    pending = core.bus.get_pending(agent_id) if hasattr(core, 'bus') else []
    return {
        "id": agent.agent_id,
        "model_key": agent.model_key,
        "model_size": agent.model_size.value,
        "state": agent.state.value,
        "can_use_tools": agent.can_use_tools,
        "capabilities": agent.definition.capabilities,
        "pending_messages": len(pending),
        "pending_message_types": [m.msg_type.value for m in pending] if pending else [],
    }


@router.get("/api/missions/{mission_id}", dependencies=[Depends(verify_api_key)])
async def get_mission(mission_id: str):
    """Get mission details including messages and workspace entries."""
    core = get_core()
    result = {"mission_id": mission_id}
    if hasattr(core, 'scheduler') and core.scheduler:
        mission = core.scheduler.get_mission(mission_id)
        if mission:
            result["status"] = mission.get("status")
            result["total_tasks"] = mission.get("total_tasks")
            result["completed_tasks"] = mission.get("completed_tasks")
            result["created_at"] = mission.get("created_at")
            result["results"] = {k: {"model": v.get("model"), "task": v.get("task", "")[:200]} for k, v in mission.get("results", {}).items()}
    if hasattr(core, 'bus') and core.bus:
        msgs = core.bus.get_mission_messages(mission_id)
        result["messages"] = [m.to_dict() for m in msgs[-50:]]
    if hasattr(core, 'workspace') and core.workspace:
        entries = core.workspace.query(mission_id)
        result["workspace_entries"] = [e.to_dict() for e in entries]
    return result


@router.get("/api/workspace/{mission_id}", dependencies=[Depends(verify_api_key)])
async def get_workspace(mission_id: str):
    """Get workspace entries for a mission."""
    core = get_core()
    if not hasattr(core, 'workspace') or not core.workspace:
        return []
    entries = core.workspace.query(mission_id)
    return [e.to_dict() for e in entries]


@router.get("/api/cognitive/status", dependencies=[Depends(verify_api_key)])
async def cognitive_status():
    """Get cognitive loop status."""
    core = get_core()
    if core.cognitive_loop:
        return core.cognitive_loop.get_status()
    return {"running": False, "phase": "disabled"}
