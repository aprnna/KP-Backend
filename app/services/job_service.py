"""
Job Service for managing scraping jobs.
Handles job lifecycle, progress updates, and logging.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ScrapingJob, JobStatus, JobSource


logger = logging.getLogger(__name__)


class JobService:
    """
    Service for managing scraping jobs.
    Provides methods for:
    - Creating new jobs
    - Updating job status and progress
    - Querying and listing jobs
    - Enforcing single-job concurrency via SELECT FOR UPDATE guard
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_no_running_jobs(self) -> bool:
        """
        Verify no scraping job is currently in RUNNING state.

        Uses SELECT FOR UPDATE to prevent a TOCTOU race condition where two
        concurrent API requests both read running_count == 0 before either
        creates a new job.

        Returns:
            True if no job is running (safe to start a new one).
            False if a job is already running.
        """
        running_count_result = await self.db.execute(
            select(func.count(ScrapingJob.id))
            .where(ScrapingJob.status == JobStatus.RUNNING)
            .with_for_update()
        )
        running_count = running_count_result.scalar_one()
        return running_count == 0

    async def create_job(
        self,
        source: JobSource = JobSource.BOTH,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ScrapingJob:
        """
        Create a new scraping job.

        Args:
            source: Data source (sinta_articles, sinta_authors, or both)
            parameters: Job parameters (e.g., year_start, year_end)

        Returns:
            Created ScrapingJob instance
        """
        job = ScrapingJob(
            job_id=str(uuid.uuid4()),
            source=source,
            status=JobStatus.PENDING,
            parameters=parameters,
            created_at=datetime.utcnow(),
        )

        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        logger.info("job_created", extra={"job_id": job.job_id, "source": source})

        return job

    async def start_job(self, job_id: str) -> Optional[ScrapingJob]:
        """
        Mark job as running.

        Args:
            job_id: Job UUID

        Returns:
            Updated job or None if not found
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        await self.db.flush()

        logger.info("job_started", extra={"job_id": job_id})
        return job

    async def update_progress(
        self,
        job_id: str,
        processed: int,
        total: Optional[int] = None,
    ) -> Optional[ScrapingJob]:
        """
        Update job progress.

        Args:
            job_id: Job UUID
            processed: Number of records processed
            total: Total records (optional, updates if provided)

        Returns:
            Updated job or None if not found
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None

        job.processed_records = processed
        if total is not None:
            job.total_records = total

        await self.db.flush()
        return job

    async def finish_job(
        self,
        job_id: str,
        total_processed: int,
    ) -> Optional[ScrapingJob]:
        """
        Mark job as finished successfully.

        Args:
            job_id: Job UUID
            total_processed: Final count of processed records

        Returns:
            Updated job or None if not found
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None

        job.status = JobStatus.FINISHED
        job.finished_at = datetime.utcnow()
        job.processed_records = total_processed

        await self.db.flush()

        logger.info(
            "job_finished",
            extra={"job_id": job_id, "total_records": total_processed},
        )
        return job

    async def fail_job(
        self,
        job_id: str,
        error_message: str,
    ) -> Optional[ScrapingJob]:
        """
        Mark job as failed.

        Args:
            job_id: Job UUID
            error_message: Error description

        Returns:
            Updated job or None if not found
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None

        job.status = JobStatus.FAILED
        job.finished_at = datetime.utcnow()
        job.error_message = error_message

        await self.db.flush()

        logger.error("job_failed", extra={"job_id": job_id, "error": error_message})
        return job

    async def get_job_by_uuid(self, job_id: str) -> Optional[ScrapingJob]:
        """
        Get job by UUID.

        Args:
            job_id: Job UUID

        Returns:
            ScrapingJob or None if not found
        """
        result = await self.db.execute(
            select(ScrapingJob).where(ScrapingJob.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job_with_logs(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job with logs payload.

        Args:
            job_id: Job UUID

        Returns:
            Dictionary with job data and logs, or None if not found
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None

        return {"job": job, "logs": []}

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        source: Optional[JobSource] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ScrapingJob]:
        """
        List jobs with optional filters.

        Args:
            status: Filter by status
            source: Filter by source
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of ScrapingJob instances
        """
        query = select(ScrapingJob)

        if status:
            query = query.where(ScrapingJob.status == status)
        if source:
            query = query.where(ScrapingJob.source == source)

        query = query.order_by(desc(ScrapingJob.created_at))
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_running_jobs_count(self) -> int:
        """Get count of currently running jobs."""
        result = await self.db.execute(
            select(ScrapingJob).where(ScrapingJob.status == JobStatus.RUNNING)
        )
        jobs = result.scalars().all()
        return len(jobs)
