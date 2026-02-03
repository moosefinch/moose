"""Scheduled jobs endpoints."""

import re

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key, get_core
from models import ScheduledJobCreate, ScheduledJobUpdate, NaturalScheduleRequest

router = APIRouter()


@router.get("/api/scheduled-jobs", dependencies=[Depends(verify_api_key)])
async def list_scheduled_jobs():
    core = get_core()
    cron = getattr(core, '_cron_scheduler', None)
    if not cron:
        return []
    return cron.list_jobs()


@router.post("/api/scheduled-jobs", dependencies=[Depends(verify_api_key)])
async def create_scheduled_job(req: ScheduledJobCreate):
    core = get_core()
    cron = getattr(core, '_cron_scheduler', None)
    if not cron:
        raise HTTPException(status_code=503, detail="Cron scheduler not initialized")
    result = cron.create_job(
        description=req.description,
        schedule_type=req.schedule_type,
        schedule_value=req.schedule_value,
        agent_id=req.agent_id or "",
        task_payload=req.task_payload or "",
    )
    return result


@router.patch("/api/scheduled-jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def update_scheduled_job(job_id: str, req: ScheduledJobUpdate):
    core = get_core()
    cron = getattr(core, '_cron_scheduler', None)
    if not cron:
        raise HTTPException(status_code=503, detail="Cron scheduler not initialized")
    kwargs = req.model_dump(exclude_none=True)
    result = cron.update_job(job_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.delete("/api/scheduled-jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def delete_scheduled_job(job_id: str):
    core = get_core()
    cron = getattr(core, '_cron_scheduler', None)
    if not cron:
        raise HTTPException(status_code=503, detail="Cron scheduler not initialized")
    success = cron.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "id": job_id}


def _parse_natural_schedule(text: str) -> dict | None:
    """Parse common natural language schedule patterns into schedule_type + schedule_value.

    Supported patterns:
      - "every N minutes/hours/seconds"
      - "daily at HH:MM"
      - "every Monday/Tuesday/... at HH:MM"
      - "in N minutes/hours"
    """
    text = text.strip().lower()

    # "every N minutes/hours/seconds"
    m = re.match(r"every\s+(\d+)\s+(second|minute|hour)s?", text)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        multiplier = {"second": 1, "minute": 60, "hour": 3600}[unit]
        return {"schedule_type": "interval", "schedule_value": str(n * multiplier)}

    # "daily at HH:MM"
    m = re.match(r"daily\s+at\s+(\d{1,2}):(\d{2})", text)
    if m:
        hour, minute = m.group(1), m.group(2)
        return {"schedule_type": "cron", "schedule_value": f"{minute} {hour} * * *"}

    # "every <weekday> at HH:MM"
    days = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
            "thursday": 4, "friday": 5, "saturday": 6}
    m = re.match(r"every\s+(\w+)\s+at\s+(\d{1,2}):(\d{2})", text)
    if m:
        day_name = m.group(1)
        if day_name in days:
            hour, minute = m.group(2), m.group(3)
            return {"schedule_type": "cron", "schedule_value": f"{minute} {hour} * * {days[day_name]}"}

    # "in N minutes/hours"
    m = re.match(r"in\s+(\d+)\s+(minute|hour)s?", text)
    if m:
        from datetime import datetime, timezone, timedelta
        n = int(m.group(1))
        unit = m.group(2)
        multiplier = {"minute": 60, "hour": 3600}[unit]
        run_at = datetime.now(timezone.utc) + timedelta(seconds=n * multiplier)
        return {"schedule_type": "once", "schedule_value": run_at.isoformat()}

    return None


@router.post("/api/scheduled-jobs/parse-natural", dependencies=[Depends(verify_api_key)])
async def parse_natural_schedule(req: NaturalScheduleRequest):
    result = _parse_natural_schedule(req.text)
    if result is None:
        raise HTTPException(status_code=422, detail="Could not parse schedule from text")
    return result
