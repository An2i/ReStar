from fastapi import FastAPI

from backend.routes import health, knowledge, manager, skills, status, tools
from backend.routes.frontend import mount_frontend_assets, router as frontend_router
from backend.state import (
    start_background_workers,
    stop_background_workers,
)


def create_app() -> FastAPI:
    app = FastAPI(title="CodeX Web Platform", version="0.1.0")

    app.add_event_handler("startup", start_background_workers)
    app.add_event_handler("shutdown", stop_background_workers)

    app.include_router(health.router)
    app.include_router(manager.router)
    app.include_router(tools.router)
    app.include_router(status.router)
    app.include_router(knowledge.router)
    app.include_router(skills.router)
    mount_frontend_assets(app)
    app.include_router(frontend_router)

    return app


app = create_app()
