"""
Moose — Local-first, security-centric engineering assistant.
FastAPI backend with LM Studio HTTP API orchestration.
"""

import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from auth import MOOSE_API_KEY, set_app
from core import AgentCore
from network import is_allowed_source
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


app = FastAPI(
    title="Moose",
    description="Local-first, security-centric multi-agent AI engineering assistant API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)
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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


class NetworkACLMiddleware(BaseHTTPMiddleware):
    """Reject requests from non-Tailscale, non-localhost sources.

    Defence-in-depth: even if Moose is accidentally bound to a LAN
    interface, only loopback and Tailscale CGNAT (100.64/10) IPs are
    allowed through.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else None
        if client_ip and not is_allowed_source(client_ip):
            logger.warning("Blocked request from non-Tailscale IP: %s %s",
                           client_ip, request.url.path)
            return Response(status_code=403, content="Forbidden")
        return await call_next(request)


app.add_middleware(NetworkACLMiddleware)


class AuditMiddleware(BaseHTTPMiddleware):
    """Log security-relevant API requests to audit log."""

    # Endpoints to audit (security-sensitive operations)
    AUDIT_ENDPOINTS = {
        "/api/query",
        "/api/key/rotate",
        "/api/key/status",
        "/api/tasks",
        "/api/files",
        "/ws",
        "/v1/chat/completions",
        "/v1/models",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only audit specific endpoints
        path = request.url.path
        if any(path.startswith(ep) for ep in self.AUDIT_ENDPOINTS):
            try:
                from audit import audit
                audit(
                    "api_request",
                    ip_address=request.client.host if request.client else None,
                    endpoint=path,
                    method=request.method,
                    status_code=response.status_code,
                )
            except Exception:
                pass  # Don't let audit failures break requests

        return response


app.add_middleware(AuditMiddleware)

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
    from network import get_bind_host
    _host = get_bind_host()
    uvicorn.run(app, host=_host, port=8000)
