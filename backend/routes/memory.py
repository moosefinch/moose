"""Memory search endpoint."""

from fastapi import APIRouter, Depends

from auth import verify_api_key, get_core

router = APIRouter()


@router.get("/api/memory", dependencies=[Depends(verify_api_key)])
async def api_memory_search(q: str = "", top_k: int = 10):
    core = get_core()
    if q:
        results = await core.memory.search(q, top_k=top_k)
        return {"results": results}
    return {"count": core.memory.count()}
