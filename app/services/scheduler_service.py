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
from app.core.database import get_db_context
from app.services.job_service import JobService
from app.services.scraping_service import ScrapingService
from app.models.job import JobSource


logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the global scheduler instance."""
    return scheduler


async def monthly_scrape_job():
    """
    Monthly scraping job function.
    Triggered by scheduler on configured day of month.
    Uses the same logic as manual trigger.
    """
    logger.info("Starting scheduled monthly scraping job")
    
    try:
        async with get_db_context() as db:
            job_service = JobService(db)
            scraping_service = ScrapingService(db, job_service)
            
            # Create a scheduled job with default parameters
            job = await job_service.create_job(
                source=JobSource.BOTH,
                parameters={
                    "year_start": settings.year_start,
                    "year_end": settings.year_end,
                    "triggered_by": "scheduler",
                    "schedule": f"day {settings.scrape_day_of_month} of month",
                }
            )
            
            logger.info(f"Scheduled job created: {job.job_id}")
            
            # Run the scraping (this will run in background)
            await scraping_service.run_scraping_job(job.job_id)
            
            logger.info(f"Scheduled scraping job {job.job_id} completed")
            
    except Exception as e:
        logger.error(f"Error in scheduled scraping job: {e}", exc_info=True)
        raise


def job_listener(event):
    """Listener for scheduler job events."""
    if event.exception:
        logger.error(f"Scheduled job failed: {event.exception}")
    else:
        logger.info(f"Scheduled job completed: {event.job_id}")


def setup_scheduler() -> Optional[AsyncIOScheduler]:
    """
    Set up and configure the scheduler.
    
    Returns:
        Configured scheduler instance or None if disabled
    """
    global scheduler
    
    if not settings.scheduler_enabled:
        logger.info("Scheduler is disabled")
        return None
    
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,  # 1 hour grace time
        }
    )
    
    # Add monthly scraping job
    # Runs on configured day of month at 02:00 UTC
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
    
    # Add event listener
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    
    logger.info(
        f"Scheduler configured: monthly scrape on day {settings.scrape_day_of_month} at 02:00 UTC"
    )
    
    return scheduler


def start_scheduler():
    """Start the scheduler if configured."""
    global scheduler
    
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown")


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.
    
    Returns:
        Dictionary with scheduler status info
    """
    global scheduler
    
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
