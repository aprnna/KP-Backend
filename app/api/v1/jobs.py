"""
Jobs API routes.
Endpoints for querying scraping job status.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.job_service import JobService
from app.models.job import JobStatus, JobSource
from app.api.schemas import (
    JobSchema,
    JobDetailResponse,
    JobListResponse,
    JobLogSchema,
    JobStatusEnum,
    JobSourceEnum,
    ErrorResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter()


def job_to_schema(job) -> JobSchema:
    """Convert ScrapingJob model to JobSchema."""
    return JobSchema(
        job_id=job.job_id,
        source=JobSourceEnum(job.source.value),
        status=JobStatusEnum(job.status.value),
        total_records=job.total_records,
        processed_records=job.processed_records,
        progress_percentage=job.progress_percentage,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=job.duration_seconds,
        error_message=job.error_message,
        parameters=job.parameters,
    )


def log_to_schema(log) -> JobLogSchema:
    """Convert ScrapingLog model to JobLogSchema."""
    return JobLogSchema(
        id=log.id,
        level=log.level.value if hasattr(log.level, 'value') else str(log.level),
        message=log.message,
        extra_data=log.extra_data,
        created_at=log.created_at,
    )


@router.get(
    "",
    response_model=JobListResponse,
    summary="List Scraping Jobs",
    description="Get a list of all scraping jobs with optional filters."
)
async def list_jobs(
    status: Optional[JobStatusEnum] = Query(
        None,
        description="Filter by job status"
    ),
    source: Optional[JobSourceEnum] = Query(
        None,
        description="Filter by data source"
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum number of results"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Offset for pagination"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List all scraping jobs.
    
    Supports filtering by status and source, with pagination.
    """
    job_service = JobService(db)
    
    # Convert string enums to model enums
    status_filter = JobStatus(status.value) if status else None
    source_filter = JobSource(source.value) if source else None
    
    jobs = await job_service.list_jobs(
        status=status_filter,
        source=source_filter,
        limit=limit,
        offset=offset,
    )
    
    job_schemas = [job_to_schema(job) for job in jobs]
    
    return JobListResponse(
        jobs=job_schemas,
        total=len(job_schemas),  # TODO: implement total count query
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
    summary="Get Job Details",
    description="Get detailed information about a specific scraping job, including logs."
)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed status of a specific job.
    
    Includes job metadata and recent logs.
    """
    job_service = JobService(db)
    
    result = await job_service.get_job_with_logs(job_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found"
        )
    
    job = result["job"]
    logs = result["logs"]
    
    return JobDetailResponse(
        job=job_to_schema(job),
        logs=[log_to_schema(log) for log in logs],
    )


@router.get(
    "/{job_id}/logs",
    response_model=list[JobLogSchema],
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
    summary="Get Job Logs",
    description="Get logs for a specific scraping job."
)
async def get_job_logs(
    job_id: str,
    level: Optional[str] = Query(
        None,
        description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of logs"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get logs for a specific job.
    """
    job_service = JobService(db)
    
    result = await job_service.get_job_with_logs(job_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id '{job_id}' not found"
        )
    
    logs = result["logs"]
    
    # Filter by level if specified
    if level:
        logs = [log for log in logs if log.level.value == level.upper()]
    
    # Limit results
    logs = logs[:limit]
    
    return [log_to_schema(log) for log in logs]
