"""FastAPI application for SkillNexus."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from skillnexus.api.dependencies import initialize
from skillnexus.api.routes import skills, analysis, evolution
from skillnexus.config.settings import Settings
from skillnexus.utils.logging import Logger

logger = Logger.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    settings: Optional[Settings] = app.state.settings if hasattr(app.state, "settings") else None
    skill_dirs: Optional[list[Path]] = app.state.skill_dirs if hasattr(app.state, "skill_dirs") else None
    initialize(settings=settings, skill_dirs=skill_dirs)
    yield
    # Shutdown
    from skillnexus.api.dependencies import get_store, get_evolver
    try:
        evolver = get_evolver()
        await evolver.wait_background()
    except Exception:
        pass
    try:
        store = get_store()
        store.close()
    except Exception:
        pass


def create_app(
    settings: Optional[Settings] = None,
    skill_dirs: Optional[list[Path]] = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="SkillNexus",
        description="Enterprise skill sharing and evolution platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store config for lifespan
    app.state.settings = settings
    app.state.skill_dirs = skill_dirs

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
    app.include_router(evolution.router, prefix="/api/evolution", tags=["evolution"])

    @app.get("/")
    async def root():
        return {"name": "SkillNexus", "version": "0.1.0"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
