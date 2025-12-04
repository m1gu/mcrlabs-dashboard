"""FastAPI app factory for the Downloader QBench Data API."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from downloader_qbench_data.config import get_settings
from .routers import analytics, entities, metrics, auth as auth_router

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure a FastAPI application instance."""

    settings = get_settings()
    LOGGER.info("Initialising FastAPI application for Downloader QBench Data")

    app = FastAPI(
        title="Downloader QBench Data API",
        version="1.0.0",
        description="REST API providing metrics and details for QBench data syncs.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    allowed_origins = {
        "https://615c98lc-8000.use.devtunnels.ms",
        "https://615c98lc-5177.use.devtunnels.ms",
        "http://localhost:5173",
        "http://localhost:5177",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5177",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    }

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")
    app.include_router(entities.router, prefix="/api/v1")

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        LOGGER.info("Serving dashboard static files from %s", frontend_dist)
        app.mount(
            "/dashboard",
            StaticFiles(directory=frontend_dist, html=True),
            name="dashboard",
        )

        @app.get("/", include_in_schema=False)
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/dashboard/", status_code=307)
    else:
        LOGGER.warning("Frontend build not found at %s; dashboard route disabled", frontend_dist)

    return app
