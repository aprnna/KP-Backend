"""
Scrape API routes.
Endpoints for triggering and managing scraping operations.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key
from app.core.config import settings
from app.services.job_service import JobService
from app.services.scraping_service import ScrapingService
from app.models.job import JobSource
from app.api.schemas import ScrapeRequest, ScrapeResponse, JobStatusEnum, ErrorResponse


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=ScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid API Key"},
        422: {"model": ErrorResponse, "description": "Validation Error"},
        503: {"model": ErrorResponse, "description": "Service Unavailable"},
    },
    summary="Trigger Scraping Job",
    description="""
    Trigger a new scraping job for academic data.
    
    The job runs in the background and can be monitored via the `/jobs/{job_id}` endpoint.
    
    **Authentication**: Requires `X-API-Key` header.
    
    **Sources**:
    - `crossref`: Scrape publications from Crossref API
    - `openalex`: Scrape author data from OpenAlex API  
    - `both`: Scrape from both sources (default)
    """,
)
async def trigger_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
) -> ScrapeResponse:
    """
    Trigger a manual scraping job.

    Returns job_id for tracking progress.
    """
    job_service = JobService(db)

    # Delegate the running-job guard to the service layer (business logic belongs there)
    no_running = await job_service.check_no_running_jobs()
    if not no_running:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A scraping job is already running. Please wait for it to complete.",
        )

    # Map request source to JobSource enum
    source_map = {
        "crossref": JobSource.CROSSREF,
        "openalex": JobSource.OPENALEX,
        "both": JobSource.BOTH,
    }
    source = source_map.get(request.source.value, JobSource.BOTH)

    # Prepare parameters
    parameters = {
        "year_start": request.year_start or settings.year_start,
        "year_end": request.year_end or settings.year_end,
        "triggered_by": "api",
    }

    if request.authors:
        parameters["authors"] = request.authors

    if request.filter_unikom is not None:
        parameters["filter_unikom"] = request.filter_unikom

    # Create the job
    job = await job_service.create_job(
        source=source,
        parameters=parameters,
    )

    await db.commit()

    # Schedule background task
    background_tasks.add_task(
        run_scraping_background,
        job.job_id,
        request.authors,
    )

    logger.info("scrape_job_scheduled", extra={"job_id": job.job_id, "source": source})

    return ScrapeResponse(
        job_id=job.job_id,
        status=JobStatusEnum.PENDING,
        message="Scraping job created successfully. Use /jobs/{job_id} to monitor progress.",
        created_at=job.created_at,
    )


async def run_scraping_background(job_id: str, authors: Optional[list[str]] = None) -> None:
    """
    Background task to run scraping.

    ScrapingService manages its own session lifecycle internally —
    no long-lived session is passed in from outside.
    """
    try:
        scraping_service = ScrapingService()
        await scraping_service.run_scraping_job(job_id)
    except Exception as e:
        logger.error(
            "background_scraping_failed",
            extra={"job_id": job_id, "error": str(e)},
            exc_info=True,
        )
