"""
FastAPI application server configuration.
Sets up middlewares, routes, lifespan events, and logging.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import update

import time
import logging

from app.api import health_route
from app.api.v1.router import router_v1
from app.core.config import settings
from app.core.database import init_db, close_db, async_session_maker
from app.models.job import ScrapingJob, JobStatus


logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=settings.log_format
    )


def setup_middlewares(app: FastAPI):
    """Configure application middlewares."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts_list
        )
    
    @app.middleware("http")
    async def add_timing(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        
        logger.info(f"{request.method} {request.url.path} - {response.status_code} ({process_time:.4f}s)")
        return response
    
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block"
        })
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting application...")

    # Setup logging
    setup_logging()

    # Initialize main database
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # --- Stale job recovery ---
    # Any job left in RUNNING state from a previous server crash is a zombie
    # that would permanently block new scrape requests. Reset them to FAILED.
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                update(ScrapingJob)
                .where(ScrapingJob.status == JobStatus.RUNNING)
                .values(
                    status=JobStatus.FAILED,
                    finished_at=datetime.utcnow(),
                    error_message="Server restarted while job was running",
                )
            )
            await session.commit()
            if result.rowcount:
                logger.warning(
                    f"Recovered {result.rowcount} stale RUNNING job(s) → FAILED"
                )
    except Exception as e:
        logger.error(f"Stale job recovery failed: {e}")

    # Start scheduler
    try:
        from app.services.scheduler_service import setup_scheduler, start_scheduler
        setup_scheduler()
        start_scheduler()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Scheduler initialization failed: {e}")

    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Stop scheduler
    try:
        from app.services.scheduler_service import shutdown_scheduler
        shutdown_scheduler()
        logger.info("Scheduler stopped")
    except Exception as e:
        logger.error(f"Scheduler shutdown error: {e}")
    
    # Close database connections
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Database shutdown error: {e}")
    
    logger.info("Application shutdown complete")


def index_route(app) -> FastAPI:
    """Define the index route for the FastAPI application"""
    @app.get("/", tags=["welcome"])
    def _():
        return {
            "message": "Welcome to the Academic Scraper API!",
            "version": settings.version,
            "environment": settings.environment,
            "docs": "/docs",
        }

    return app


def v1_route(app) -> FastAPI:
    app.include_router(
        router_v1,
        prefix="/api/v1",
        tags=["v1"]
    )
    return app


def create_application() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title=settings.app_name,
        description="""
        Academic Data Scraping Service API.

        This service scrapes academic data from:
        - **SINTA**: Author profiles, bibliometrics, and publication lists

        Results are stored in a dedicated scraping database (`sinta_articles`, `sinta_authors`).

        ## Features
        - Manual and scheduled scraping
        - Job tracking with progress updates
        - Idempotent data storage (upsert)
        - Rate limiting and retry logic

        ## Authentication
        Protected endpoints require `X-API-Key` header.
        """,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    setup_middlewares(app)
    index_route(app)

    app.include_router(health_route.router)
    
    v1_route(app)
    
    logger.info("FastAPI application configured successfully")

    return app