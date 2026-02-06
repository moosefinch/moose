"""
Route registration — includes all API routers into the FastAPI app.
"""

from fastapi import FastAPI

from routes.health import router as health_router
from routes.chat import router as chat_router
from routes.conversations import router as conversations_router
from routes.memory import router as memory_router
from routes.tasks import router as tasks_router
from routes.agents import router as agents_router
from routes.files import router as files_router
from routes.channels import router as channels_router
from routes.approvals import router as approvals_router
from routes.overlays import router as overlays_router
from routes.marketing import router as marketing_router
from routes.email import router as email_router
from routes.jobs import router as jobs_router
from routes.voice import router as voice_router
from routes.plugins import router as plugins_router
from routes.webhooks import router as webhooks_router
from routes.printer import router as printer_router
from routes.openai_compat import router as openai_compat_router
from routes.advocacy import router as advocacy_router
from routes.proposals import router as proposals_router


def register_routes(app: FastAPI):
    """Mount all API routers onto the app."""
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(memory_router)
    app.include_router(tasks_router)
    app.include_router(agents_router)
    app.include_router(files_router)
    app.include_router(channels_router)
    app.include_router(approvals_router)
    app.include_router(overlays_router)
    app.include_router(marketing_router)
    app.include_router(email_router)
    app.include_router(jobs_router)
    app.include_router(voice_router)
    app.include_router(plugins_router)
    app.include_router(webhooks_router)
    app.include_router(printer_router)
    app.include_router(openai_compat_router)
    app.include_router(advocacy_router)
    app.include_router(proposals_router)
