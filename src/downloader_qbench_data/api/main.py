"""FastAPI app factory for the Downloader QBench Data API."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from downloader_qbench_data.config import get_settings
from .routers import analytics, entities, metrics, auth as auth_router
from .routers import glims_overview, glims_priority, glims_tat, glims_status

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
    app.include_router(glims_overview.router)
    app.include_router(glims_priority.router)
    app.include_router(glims_tat.router)
    app.include_router(glims_status.router)

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        LOGGER.info("Serving dashboard static files from %s", frontend_dist)
        
        # 1. Mount assets specifically (better performance, avoids catch-all for these)
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount(
                "/dashboard/assets",
                StaticFiles(directory=assets_dir),
                name="dashboard_assets",
            )

        # 2. Redirect root to dashboard
        @app.get("/", include_in_schema=False)
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/dashboard/", status_code=307)

        # 3. Catch-all for /dashboard/* to serve index.html (SPA Fallback)
        @app.get("/dashboard/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            # Check if a physical file exists (e.g. vite.svg, favicon.ico)
            file_path = frontend_dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            
            # Otherwise return index.html for client-side routing
            return FileResponse(frontend_dist / "index.html")

        # Handle exact /dashboard request too
        @app.get("/dashboard", include_in_schema=False)
        async def serve_spa_root() -> FileResponse:
             return FileResponse(frontend_dist / "index.html")
    else:
        LOGGER.warning("Frontend build not found at %s; dashboard route disabled", frontend_dist)

    return app
