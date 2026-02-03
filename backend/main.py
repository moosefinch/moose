"""
Moose — Local-first, security-centric engineering assistant.
FastAPI backend with LM Studio HTTP API orchestration.
"""

import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from auth import MOOSE_API_KEY, set_app
from core import AgentCore
from schema import init_db
from routes import register_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    init_db()
    _redacted = MOOSE_API_KEY[-4:] if len(MOOSE_API_KEY) > 4 else "****"
    logger.info("API key: ****...%s", _redacted)
    logger.info("Set X-API-Key header to authenticate.")
    core = AgentCore()
    app.state.agent_core = core
    try:
        await core.start()
    except Exception as e:
        logger.error("Startup error: %s", e)
    yield
    await core.shutdown()


app = FastAPI(title="Moose", lifespan=lifespan)
set_app(app)

from profile import get_profile as _get_cors_profile
_cors_profile = _get_cors_profile()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_profile.web.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app)


# ── Serve frontend static build (production) ──
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        dist_resolved = FRONTEND_DIST.resolve()
        file_path = (FRONTEND_DIST / full_path).resolve()
        if full_path and str(file_path).startswith(str(dist_resolved)) and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"error": "Frontend not built"}

    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
