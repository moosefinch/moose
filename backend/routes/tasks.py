"""Task and briefing endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, require_ready, get_core
from db import db_connection
from models import TaskRequest

router = APIRouter()


@router.post("/api/task", dependencies=[Depends(verify_api_key), Depends(require_ready)])
async def start_task(req: TaskRequest):
    core = get_core()
    bg_task = await core.start_task(req.description, req.plan)

    with db_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO tasks (id, description, status, plan, progress_log, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bg_task.id, bg_task.description, bg_task.status,
             json.dumps(bg_task.plan), json.dumps(bg_task.progress_log),
             bg_task.created_at, bg_task.updated_at))
        conn.commit()

    return {"id": bg_task.id, "description": bg_task.description, "status": bg_task.status, "created_at": bg_task.created_at}


@router.get("/api/task/{task_id}", dependencies=[Depends(verify_api_key)])
async def get_task(task_id: str):
    core = get_core()
    task = core.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.get("/api/tasks", dependencies=[Depends(verify_api_key)])
async def list_tasks():
    core = get_core()
    return core.list_tasks()


@router.delete("/api/task/{task_id}", dependencies=[Depends(verify_api_key)])
async def cancel_task(task_id: str):
    core = get_core()
    success = core.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or not running")
    return {"status": "cancelled", "id": task_id}


@router.get("/api/briefings", dependencies=[Depends(verify_api_key)])
async def get_briefings(unread_only: bool = False):
    core = get_core()
    return core.get_briefings(unread_only=unread_only)


@router.post("/api/briefings/{briefing_id}/read", dependencies=[Depends(verify_api_key)])
async def mark_briefing_read(briefing_id: str):
    core = get_core()
    success = core.mark_briefing_read(briefing_id)
    if not success:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return {"status": "read", "id": briefing_id}
