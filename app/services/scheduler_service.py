"""
Scheduler Service for automated monthly scraping.
Uses APScheduler with AsyncIOScheduler.
"""

import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from app.core.config import settings
from app.models.job import JobSource


logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the global scheduler instance."""
    return scheduler


async def monthly_scrape_job() -> None:
    """
    Monthly scraping job function.
    Triggered by scheduler on configured day of month.
    ScrapingService manages its own session lifecycle internally.
    """
    logger.info("scheduled_scrape_start")

    try:
        from app.core.database import async_session_maker
        from app.services.job_service import JobService

        # Create the job record in its own short-lived session
        async with async_session_maker() as db:
            job_service = JobService(db)
            job = await job_service.create_job(
                source=JobSource.BOTH,
                parameters={
                    "year_start": settings.year_start,
                    "year_end": settings.year_end,
                    "triggered_by": "scheduler",
                    "schedule": f"day {settings.scrape_day_of_month} of month",
                },
            )
            await db.commit()

        logger.info("scheduled_job_created", extra={"job_id": job.job_id})

        # Run the scraping — ScrapingService creates its own sessions
        from app.services.scraping_service import ScrapingService
        scraping_service = ScrapingService()
        await scraping_service.run_scraping_job(job.job_id)

        logger.info("scheduled_scrape_complete", extra={"job_id": job.job_id})

    except Exception as e:
        logger.error(
            "scheduled_scrape_error",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


def job_listener(event) -> None:
    """Listener for scheduler job events."""
    if event.exception:
        logger.error(
            "scheduler_job_failed",
            extra={"scheduled_job_id": event.job_id, "error": str(event.exception)},
        )
    else:
        logger.info(
            "scheduler_job_executed",
            extra={"scheduled_job_id": event.job_id},
        )


def setup_scheduler() -> Optional[AsyncIOScheduler]:
    """
    Set up and configure the scheduler.

    Returns:
        Configured scheduler instance or None if disabled
    """
    global scheduler

    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return None

    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,  # 1 hour grace time
        },
    )

    # Add monthly scraping job — runs on configured day of month at 02:00 UTC
    scheduler.add_job(
        monthly_scrape_job,
        CronTrigger(
            day=settings.scrape_day_of_month,
            hour=2,
            minute=0,
        ),
        id="monthly_scrape",
        name="Monthly Academic Data Scraping",
        replace_existing=True,
    )

    # Add event listener for success/failure tracking
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    logger.info(
        "scheduler_configured",
        extra={
            "scrape_day_of_month": settings.scrape_day_of_month,
            "time_utc": "02:00",
        },
    )

    return scheduler


def start_scheduler() -> None:
    """Start the scheduler if configured."""
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("scheduler_started")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_shutdown")


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.

    Returns:
        Dictionary with scheduler status info
    """
    if not scheduler:
        return {
            "enabled": False,
            "running": False,
            "jobs": [],
        }

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })

    return {
        "enabled": settings.scheduler_enabled,
        "running": scheduler.running,
        "jobs": jobs,
        "scrape_day_of_month": settings.scrape_day_of_month,
    }
