"""
Job Service for managing scraping jobs.
Handles job lifecycle, progress updates, and logging.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import ScrapingJob, ScrapingLog, JobStatus, JobSource, LogLevel


logger = logging.getLogger(__name__)


class JobService:
    """
    Service for managing scraping jobs.
    Provides methods for:
    - Creating new jobs
    - Updating job status and progress
    - Adding logs
    - Querying jobs
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        source: JobSource = JobSource.BOTH,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ScrapingJob:
        """
        Create a new scraping job.
        
        Args:
            source: Data source (crossref, openalex, or both)
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
        
        logger.info(f"Created job {job.job_id} with source={source}")
        
        # Add initial log
        await self.add_log(
            job.id,
            LogLevel.INFO,
            f"Job created with source={source}",
            {"parameters": parameters}
        )
        
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
        
        await self.add_log(
            job.id,
            LogLevel.INFO,
            "Job started"
        )
        
        logger.info(f"Job {job_id} started")
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
        
        await self.add_log(
            job.id,
            LogLevel.INFO,
            f"Job finished successfully with {total_processed} records processed"
        )
        
        logger.info(f"Job {job_id} finished with {total_processed} records")
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
        
        await self.add_log(
            job.id,
            LogLevel.ERROR,
            f"Job failed: {error_message}"
        )
        
        logger.error(f"Job {job_id} failed: {error_message}")
        return job

    async def add_log(
        self,
        job_db_id: int,
        level: LogLevel,
        message: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> ScrapingLog:
        """
        Add log entry for a job.
        
        Args:
            job_db_id: Database ID of the job
            level: Log level
            message: Log message
            extra_data: Additional data (JSON)
            
        Returns:
            Created ScrapingLog instance
        """
        log = ScrapingLog(
            job_id=job_db_id,
            level=level,
            message=message,
            extra_data=extra_data,
            created_at=datetime.utcnow(),
        )
        
        self.db.add(log)
        await self.db.flush()
        
        return log

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
        Get job with its logs.
        
        Args:
            job_id: Job UUID
            
        Returns:
            Dictionary with job data and logs
        """
        job = await self.get_job_by_uuid(job_id)
        if not job:
            return None
        
        # Fetch logs
        result = await self.db.execute(
            select(ScrapingLog)
            .where(ScrapingLog.job_id == job.id)
            .order_by(desc(ScrapingLog.created_at))
            .limit(100)
        )
        logs = result.scalars().all()
        
        return {
            "job": job,
            "logs": logs,
        }

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
