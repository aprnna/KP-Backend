"""
Health check endpoint with detailed status.
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import settings
from app.services.scheduler_service import get_scheduler_status
from app.api.schemas import HealthResponse


router = APIRouter()


@router.get(
    "/health",
    tags=["health"],
    response_model=HealthResponse,
    summary="Health Check",
    description="Check the health status of the service, database, and scheduler."
)
async def health(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.
    
    Returns:
    - Service status
    - Database connection status
    - Scheduler status
    - Current timestamp
    """
    # Check database connection
    db_status = "disconnected"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"
    
    # Get scheduler status
    scheduler_status = get_scheduler_status()
    
    return HealthResponse(
        status="healthy" if db_status == "connected" else "unhealthy",
        version=settings.version,
        environment=settings.environment,
        database=db_status,
        scheduler=scheduler_status,
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/",
    tags=["health"],
    summary="Root Endpoint",
    description="Basic root endpoint that returns service info."
)
async def root():
    """Root endpoint with basic info."""
    return {
        "name": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "docs": "/docs",
    }
