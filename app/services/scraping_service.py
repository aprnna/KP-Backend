"""
Scraping Service — orchestrates SINTA scraping jobs.

Key design decisions:
- ScrapingService uses two databases:
    * Main DB  (async_session_maker)  — job tracking, author ID lookup
    * Scrape DB (scrape_session_maker) — SINTA article/author results
- Articles are committed in bounded batches (ARTICLE_BATCH_SIZE).
- SintaAuthor rows are upserted via ON DUPLICATE KEY UPDATE.
- job.id (integer PK) is cached once at job start to avoid N+1 re-queries.
- Structured log extras on all significant events.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.database import async_session_maker
from app.models.job import ScrapingJob, JobStatus, ScrapingLog, LogLevel, JobSource
from app.models.sinta_article import SintaArticle
from app.models.sinta_author import SintaAuthor
from app.services.scraper.sinta_article import SintaArticleScraper
from app.services.scraper.sinta_author import SintaAuthorScraper


logger = logging.getLogger(__name__)

ARTICLE_BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Internal metrics dataclass
# ---------------------------------------------------------------------------

@dataclass
class JobMetrics:
    """In-memory counters logged at job completion."""
    total_sinta_ids: int = 0
    total_articles: int = 0
    total_authors_saved: int = 0
    job_start: float = field(default_factory=time.monotonic)

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.job_start


# ---------------------------------------------------------------------------
# ScrapingService
# ---------------------------------------------------------------------------

class ScrapingService:
    """
    Orchestrates SINTA scraping jobs:
    1. Resolves SINTA author IDs from the main DB
    2. Runs SintaArticleScraper and/or SintaAuthorScraper
    3. Persists results to the separate scraping database
    4. Updates job status and logs in the main DB
    """

    async def run_scraping_job(self, job_id: str) -> None:
        """
        Execute the scraping job identified by job_id.
        Called from a BackgroundTask or scheduler coroutine.
        """
        metrics = JobMetrics()
        job_db_id, params, source = await self._start_job_and_get_params(job_id)
        if job_db_id is None:
            logger.error("job_not_found", extra={"job_id": job_id})
            return

        try:
            # Check if user explicitly passed custom SINTA IDs to scrape
            sinta_ids = params.get("sinta_ids") or []
            
            # ----------------------------------------------------------------
            # SINTA Author Scraping (Phase 1 & 2)
            # ----------------------------------------------------------------
            if source in (JobSource.SINTA_AUTHORS, JobSource.BOTH):
                await self._log(job_db_id, job_id, "Starting SINTA author profile scraping natively via Affiliation…")

                async with SintaAuthorScraper() as scraper:
                    # sinta_ids=None triggers the scraper to fetch the full UNIKOM affiliation list first
                    author_results = await scraper.scrape(
                        sinta_ids=None,
                        job_id=job_id,
                        on_progress=lambda sid, p, t: asyncio.create_task(
                            self._log(job_db_id, job_id, f"Author scraping: {sid} ({p}/{t})")
                        ),
                    )

                saved_authors = await self._save_authors(job_id, job_db_id, author_results)
                metrics.total_authors_saved = saved_authors
                
                # Extract SINTA IDs for the article scraper if running BOTH
                sinta_ids = [a.get("id_sinta") for a in author_results if a.get("id_sinta")]
                metrics.total_sinta_ids = len(sinta_ids)

                await self._log(
                    job_db_id, job_id,
                    f"Author scraping done: {saved_authors}/{len(author_results)} saved.",
                )

            # ----------------------------------------------------------------
            # SINTA Article Scraping
            # ----------------------------------------------------------------
            if source in (JobSource.SINTA_ARTICLES, JobSource.BOTH):
                # If we didn't just scrape authors (i.e. running ARTICLES only),
                # we need to load the list of SINTA IDs from the sinta_authors table.
                if not sinta_ids:
                    sinta_ids = await self._resolve_sinta_ids(job_id, job_db_id)
                    metrics.total_sinta_ids = len(sinta_ids)

                await self._log(job_db_id, job_id, f"Starting SINTA article scraping for {len(sinta_ids)} authors…")

                async with SintaArticleScraper() as scraper:
                    article_results = await scraper.scrape(
                        sinta_ids=sinta_ids,
                        job_id=job_id,
                        on_progress=lambda sid, p, t: asyncio.create_task(
                            self._log(job_db_id, job_id, f"Article scraping: {sid} ({p}/{t})")
                        ),
                    )

                total_saved = await self._save_articles_batched(job_id, job_db_id, article_results)
                metrics.total_articles = total_saved
                await self._log(
                    job_db_id, job_id,
                    f"Article scraping done: {len(article_results)} found, {total_saved} saved.",
                )

            # ----------------------------------------------------------------
            # Finish
            # ----------------------------------------------------------------
            await self._finish_job(job_id, job_db_id, metrics.total_articles)

            duration = metrics.elapsed_seconds()
            logger.info(
                "scraping_job_summary",
                extra={
                    "job_id": job_id,
                    "total_sinta_ids": metrics.total_sinta_ids,
                    "total_articles": metrics.total_articles,
                    "total_authors_saved": metrics.total_authors_saved,
                    "duration_sec": round(duration, 2),
                    "source": source.value if hasattr(source, "value") else str(source),
                },
            )

        except Exception as exc:
            logger.exception("scraping_job_failed", extra={"job_id": job_id, "error": str(exc)})
            await self._fail_job(job_id, job_db_id, str(exc))

    # -----------------------------------------------------------------------
    # Main DB helpers
    # -----------------------------------------------------------------------

    async def _start_job_and_get_params(
        self, job_id: str
    ) -> tuple[Optional[int], dict, Any]:
        """Mark job RUNNING and return (db_id, parameters, source)."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScrapingJob).where(ScrapingJob.job_id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                return None, {}, None

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            session.add(ScrapingLog(
                job_id=job.id,
                level=LogLevel.INFO,
                message="Job started",
                created_at=datetime.utcnow(),
            ))
            await session.commit()
            return job.id, job.parameters or {}, job.source

    async def _resolve_sinta_ids(self, job_id: str, job_db_id: int) -> List[int]:
        """
        Fetch the list of SINTA IDs from the main `sinta_authors` table.
        These IDs drive the article scraper when it's run independently.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(SintaAuthor.id_sinta).where(SintaAuthor.id_sinta.is_not(None))
            )
            sinta_ids = [row[0] for row in result.all()]

        await self._log(
            job_db_id, job_id,
            f"Found {len(sinta_ids)} SINTA author IDs to scrape.",
        )
        return sinta_ids

    async def _finish_job(self, job_id: str, job_db_id: int, total_records: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(ScrapingJob)
                .where(ScrapingJob.job_id == job_id)
                .values(
                    status=JobStatus.FINISHED,
                    finished_at=datetime.utcnow(),
                    processed_records=total_records,
                )
            )
            session.add(ScrapingLog(
                job_id=job_db_id,
                level=LogLevel.INFO,
                message=f"Job finished — {total_records} records.",
                created_at=datetime.utcnow(),
            ))
            await session.commit()

    async def _fail_job(self, job_id: str, job_db_id: Optional[int], error: str) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(ScrapingJob)
                .where(ScrapingJob.job_id == job_id)
                .values(
                    status=JobStatus.FAILED,
                    finished_at=datetime.utcnow(),
                    error_message=error,
                )
            )
            if job_db_id is not None:
                session.add(ScrapingLog(
                    job_id=job_db_id,
                    level=LogLevel.ERROR,
                    message=f"Job failed: {error}",
                    created_at=datetime.utcnow(),
                ))
            await session.commit()

    async def _log(
        self,
        job_db_id: int,
        job_id: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
    ) -> None:
        """Append a log entry to the main DB and emit to Python logger."""
        async with async_session_maker() as session:
            session.add(ScrapingLog(
                job_id=job_db_id,
                level=level,
                message=message,
                created_at=datetime.utcnow(),
            ))
            await session.commit()

        logger.log(
            getattr(logging, level.value, logging.INFO),
            message,
            extra={"job_id": job_id},
        )

    # -----------------------------------------------------------------------
    # Scrape DB helpers
    # -----------------------------------------------------------------------

    async def _save_articles_batched(
        self,
        job_id: str,
        job_db_id: int,
        articles_data: List[Dict[str, Any]],
    ) -> int:
        """
        Persist SINTA articles to the scraping DB in bounded batches.
        Duplicate (id_sinta, source, article_title) rows are updated in-place.
        """
        total_saved = 0
        buffer: List[Dict[str, Any]] = []

        for item in articles_data:
            row = {k: v for k, v in item.items() if k != "profile_url"}
            buffer.append(row)
            if len(buffer) >= ARTICLE_BATCH_SIZE:
                total_saved += await self._flush_article_batch(buffer)
                buffer.clear()

        if buffer:
            total_saved += await self._flush_article_batch(buffer)

        return total_saved

    async def _flush_article_batch(self, batch: List[Dict[str, Any]]) -> int:
        """INSERT or UPDATE a single batch of articles in the scraping DB."""
        if not batch:
            return 0

        async with async_session_maker() as session:
            stmt = mysql_insert(SintaArticle).values(batch)
            stmt = stmt.on_duplicate_key_update(
                authors=stmt.inserted.authors,
                publisher=stmt.inserted.publisher,
                year=stmt.inserted.year,
                cited=stmt.inserted.cited,
                quartile=stmt.inserted.quartile,
                url=stmt.inserted.url,
                scraped_at=stmt.inserted.scraped_at,
            )
            await session.execute(stmt)
            await session.commit()

        return len(batch)

    async def _save_authors(
        self,
        job_id: str,
        job_db_id: int,
        authors_data: List[Dict[str, Any]],
    ) -> int:
        """
        Upsert SINTA author stats into the scraping DB.
        Uses ON DUPLICATE KEY UPDATE on id_sinta (PK).

        Returns:
            Number of rows written.
        """
        if not authors_data:
            return 0

        # Ensure all dictionary keys are present so SQLAlchemy's bulk insert
        # includes all columns in the INSERT statement, preventing UNKNOWN COLUMN errors.
        all_keys = [
            "id_sinta", "fullname", "major", 
            "sinta_score_overall", "sinta_score_3yr", "affil_score", "affil_score_3yr",
            "s_article_scopus", "s_citation_scopus", "s_cited_document_scopus", 
            "s_hindex_scopus", "s_i10_index_scopus", "s_gindex_scopus",
            "s_article_gscholar", "s_citation_gscholar", "s_cited_document_gscholar", 
            "s_hindex_gscholar", "s_i10_index_gscholar", "s_gindex_gscholar",
            "subject_research"
        ]

        clean_rows = []
        for item in authors_data:
            row = {k: item.get(k, None) for k in all_keys}
            clean_rows.append(row)

        async with async_session_maker() as session:
            stmt = mysql_insert(SintaAuthor).values(clean_rows)
            stmt = stmt.on_duplicate_key_update(
                fullname=stmt.inserted.fullname,
                major=stmt.inserted.major,
                sinta_score_overall=stmt.inserted.sinta_score_overall,
                sinta_score_3yr=stmt.inserted.sinta_score_3yr,
                affil_score=stmt.inserted.affil_score,
                affil_score_3yr=stmt.inserted.affil_score_3yr,
                s_article_scopus=stmt.inserted.s_article_scopus,
                s_citation_scopus=stmt.inserted.s_citation_scopus,
                s_cited_document_scopus=stmt.inserted.s_cited_document_scopus,
                s_hindex_scopus=stmt.inserted.s_hindex_scopus,
                s_i10_index_scopus=stmt.inserted.s_i10_index_scopus,
                s_gindex_scopus=stmt.inserted.s_gindex_scopus,
                s_article_gscholar=stmt.inserted.s_article_gscholar,
                s_citation_gscholar=stmt.inserted.s_citation_gscholar,
                s_cited_document_gscholar=stmt.inserted.s_cited_document_gscholar,
                s_hindex_gscholar=stmt.inserted.s_hindex_gscholar,
                s_i10_index_gscholar=stmt.inserted.s_i10_index_gscholar,
                s_gindex_gscholar=stmt.inserted.s_gindex_gscholar,
                subject_research=stmt.inserted.subject_research,
                scraped_at=stmt.inserted.scraped_at,
            )
            await session.execute(stmt)
            await session.commit()

        await self._log(job_db_id, job_id, f"Upserted {len(clean_rows)} author rows to scraping DB.")
        return len(clean_rows)
