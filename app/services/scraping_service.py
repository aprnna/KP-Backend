"""
Scraping Service — orchestrates scraping jobs.

Key design decisions:
- ScrapingService holds NO long-lived AsyncSession.
  Instead, every DB operation creates a fresh short-lived session via
  async_session_maker(), preventing connection-pool exhaustion.
- Articles are accumulated in a rolling buffer and persisted in batches
  of ARTICLE_BATCH_SIZE, keeping memory usage bounded.
- Concurrent Crossref scraping is handled inside CrossrefScraper itself
  (semaphore pattern); this service only drives the top-level flow.
- job.id (integer PK) is cached once at job start so _log() never
  re-queries the jobs table — eliminating the N+1 pattern.
- Structured log extras (job_id, author, source, duration_ms) are
  included on all significant events for production observability.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.database import async_session_maker
from app.models.job import ScrapingJob, JobStatus, ScrapingLog, LogLevel, JobSource
from app.models.article import Article, AuthorArticle
from app.models.author import Author
from app.services.scraper.crossref import CrossrefScraper
from app.services.scraper.openalex import OpenAlexScraper
from app.services.scraper.utils import strip_titles
from app.core.config import settings


logger = logging.getLogger(__name__)

# Articles are committed in batches to bound memory usage and
# prevent holding multi-minute DB transactions.
ARTICLE_BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Internal metrics dataclass — purely in-memory, logged at job completion
# ---------------------------------------------------------------------------

@dataclass
class JobMetrics:
    total_authors: int = 0
    total_articles: int = 0
    total_authors_saved: int = 0
    authors_matched_openalex: int = 0
    job_start: float = field(default_factory=time.monotonic)

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.job_start


# ---------------------------------------------------------------------------
# ScrapingService
# ---------------------------------------------------------------------------

class ScrapingService:
    """
    Orchestrates scraping jobs:
    1. Fetches job details and resolves authors from DB
    2. Runs selected scrapers (Crossref / OpenAlex) with proper context managers
    3. Persists results in bounded batches using short-lived sessions
    4. Updates job status and structured logs
    5. Emits a metrics summary at completion
    """

    # ScrapingService does NOT store a long-lived session;
    # it creates sessions only for each discrete DB operation.

    async def run_scraping_job(self, job_id: str) -> None:
        """
        Execute the scraping job identified by job_id.
        Should be called from a BackgroundTask or scheduler coroutine.
        """
        metrics = JobMetrics()

        # --- Start the job and resolve its integer PK in one short session ---
        job_db_id, params, source = await self._start_job_and_get_params(job_id)
        if job_db_id is None:
            logger.error("job_not_found", extra={"job_id": job_id})
            return

        try:
            authors = await self._resolve_authors(job_id, job_db_id, params)
            metrics.total_authors = len(authors)

            year_start = params.get("year_start") or settings.year_start
            year_end   = params.get("year_end")   or settings.year_end
            filter_unikom = params.get("filter_unikom")

            # ----------------------------------------------------------------
            # Crossref Scraping
            # ----------------------------------------------------------------
            if source in (JobSource.CROSSREF, JobSource.BOTH):
                await self._log(job_db_id, job_id, "Starting Crossref scraping…")

                async with CrossrefScraper(filter_unikom=filter_unikom) as cr:
                    crossref_results = await cr.scrape(
                        authors=authors,
                        year_start=year_start,
                        year_end=year_end,
                        job_id=job_id,
                        on_progress=lambda a, p, t: asyncio.create_task(
                            self._log(job_db_id, job_id, f"Crossref: {a} ({p}/{t})")
                        ),
                    )

                # Stream into DB in batches
                total_saved = await self._save_articles_batched(
                    job_id, job_db_id, crossref_results
                )
                metrics.total_articles += total_saved
                await self._log(
                    job_db_id, job_id,
                    f"Crossref done: {len(crossref_results)} articles found, {total_saved} saved."
                )

            # ----------------------------------------------------------------
            # OpenAlex Scraping
            # ----------------------------------------------------------------
            if source in (JobSource.OPENALEX, JobSource.BOTH):
                await self._log(job_db_id, job_id, "Starting OpenAlex scraping…")

                async with OpenAlexScraper() as oa:
                    openalex_results = await oa.scrape(
                        author_names=authors,
                        on_progress=lambda a, p, t: asyncio.create_task(
                            self._log(job_db_id, job_id, f"OpenAlex: {a} ({p}/{t})")
                        ),
                    )

                saved_authors = await self._save_authors(job_id, job_db_id, openalex_results)
                metrics.total_authors_saved = saved_authors
                metrics.authors_matched_openalex = sum(
                    1 for r in openalex_results if r.get("openalex_id")
                )
                await self._log(
                    job_db_id, job_id,
                    f"OpenAlex done: {metrics.authors_matched_openalex}/{len(authors)} authors matched."
                )

            # ----------------------------------------------------------------
            # Finish job
            # ----------------------------------------------------------------
            await self._finish_job(job_id, job_db_id, metrics.total_articles)

            duration = metrics.elapsed_seconds()
            logger.info(
                "scraping_job_summary",
                extra={
                    "job_id": job_id,
                    "total_authors": metrics.total_authors,
                    "total_articles": metrics.total_articles,
                    "authors_openalex": metrics.authors_matched_openalex,
                    "duration_sec": round(duration, 2),
                    "source": source.value if hasattr(source, "value") else str(source),
                },
            )

        except Exception as e:
            logger.exception("scraping_job_failed", extra={"job_id": job_id, "error": str(e)})
            await self._fail_job(job_id, job_db_id, str(e))

    # -----------------------------------------------------------------------
    # Short-lived DB helpers
    # -----------------------------------------------------------------------

    async def _start_job_and_get_params(
        self, job_id: str
    ) -> tuple[Optional[int], dict, Any]:
        """
        Mark the job as RUNNING and return (db_id, parameters, source).
        Returns (None, {}, None) if the job is not found.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScrapingJob).where(ScrapingJob.job_id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                return None, {}, None

            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()

            log = ScrapingLog(
                job_id=job.id,
                level=LogLevel.INFO,
                message="Job started",
                created_at=datetime.utcnow(),
            )
            session.add(log)
            await session.commit()

            return job.id, job.parameters or {}, job.source

    async def _resolve_authors(
        self, job_id: str, job_db_id: int, params: dict
    ) -> List[str]:
        """
        Resolve the list of authors to scrape:
        1. Read from `authors` table in DB.
        2. Fall back to request parameters or settings default.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(Author.fullname).where(Author.fullname.is_not(None))
            )
            db_authors = [row[0] for row in result.all()]

        if db_authors:
            await self._log(job_db_id, job_id, f"Found {len(db_authors)} authors in DB.")
            return db_authors

        fallback = params.get("authors") or settings.default_authors
        await self._log(
            job_db_id, job_id,
            f"No authors in DB — using {len(fallback)} from parameters.",
            level=LogLevel.WARNING,
        )
        return fallback

    async def _save_articles_batched(
        self,
        job_id: str,
        job_db_id: int,
        articles_data: List[Dict[str, Any]],
    ) -> int:
        """
        Persist articles in batches of ARTICLE_BATCH_SIZE.

        Each batch is committed in its own short-lived session.
        Uses MySQL dialect INSERT ... ON DUPLICATE KEY UPDATE on DOI column
        for true atomic upserts.

        Returns:
            Total number of rows written.
        """
        total_saved = 0
        buffer: List[Dict[str, Any]] = []

        for item in articles_data:
            row = self._map_article(item)
            buffer.append(row)

            if len(buffer) >= ARTICLE_BATCH_SIZE:
                saved = await self._flush_article_batch(buffer)
                total_saved += saved
                buffer.clear()

        # flush remaining
        if buffer:
            saved = await self._flush_article_batch(buffer)
            total_saved += saved

        # Now link author-article relations in a single pass
        await self._save_author_article_relations(job_id, job_db_id, articles_data)

        return total_saved

    async def _flush_article_batch(self, batch: List[Dict[str, Any]]) -> int:
        """
        Execute a single bulk INSERT ... ON DUPLICATE KEY UPDATE for one batch.
        The DOI column is used as the natural key; if DOI is NULL the row is
        always inserted (no de-duplication possible without a key).
        """
        if not batch:
            return 0

        async with async_session_maker() as session:
            stmt = mysql_insert(Article).values(batch)
            # Upsert all mutable fields; DOI, id_article are the keys
            stmt = stmt.on_duplicate_key_update(
                title=stmt.inserted.title,
                authors=stmt.inserted.authors,
                journal_title=stmt.inserted.journal_title,
                short_journal_title=stmt.inserted.short_journal_title,
                publisher=stmt.inserted.publisher,
                issue=stmt.inserted.issue,
                volume=stmt.inserted.volume,
                page=stmt.inserted.page,
                published=stmt.inserted.published,
                type=stmt.inserted.type,
                pdf_link=stmt.inserted.pdf_link,
                issn=stmt.inserted.issn,
                issn_type=stmt.inserted.issn_type,
                url=stmt.inserted.url,
                indexed_date_parts=stmt.inserted.indexed_date_parts,
            )
            await session.execute(stmt)
            await session.commit()

        return len(batch)

    @staticmethod
    def _map_article(item: Dict[str, Any]) -> Dict[str, Any]:
        """Map a scraped work dict to the Article table column dict."""
        published = item.get("published_date")
        return {
            "doi": item.get("doi") or None,
            "title": item.get("title"),
            "authors": item.get("authors"),
            "journal_title": item.get("container_title"),
            "short_journal_title": item.get("short_container_title"),
            "publisher": item.get("publisher"),
            "issue": item.get("issue"),
            "volume": item.get("volume"),
            "page": item.get("page"),
            "published": str(published) if published else None,
            "type": item.get("type"),
            "pdf_link": item.get("pdf_link"),
            "issn": (
                "; ".join(item["issn"])
                if isinstance(item.get("issn"), list)
                else item.get("issn")
            ),
            "issn_type": (
                "; ".join(item["issn_type"])
                if isinstance(item.get("issn_type"), list)
                else str(item.get("issn_type") or "")
            ),
            "url": item.get("url"),
            "indexed_date_parts": item.get("indexed_date_parts"),
        }

    async def _save_author_article_relations(
        self,
        job_id: str,
        job_db_id: int,
        articles_data: List[Dict[str, Any]],
    ) -> None:
        """
        Link Author ↔ Article relations using short-lived sessions.
        Author lookup uses strip_titles() to normalize names before matching,
        preventing stub-author duplication from title variants.
        """
        count_linked = 0
        async with async_session_maker() as session:
            for item in articles_data:
                doi = item.get("doi")
                raw_query_name = item.get("author_query")
                if not raw_query_name:
                    continue

                # Normalize the query name for reliable DB matching
                normalized_name = strip_titles(raw_query_name)

                # Find article by DOI (preferred) or title
                if doi:
                    art_stmt = select(Article).where(Article.doi == doi)
                else:
                    art_stmt = select(Article).where(Article.title == item.get("title"))
                art_res = await session.execute(art_stmt)
                article = art_res.scalar_one_or_none()
                if not article:
                    continue

                # Find author by normalized fullname
                auth_stmt = select(Author).where(Author.fullname == normalized_name)
                auth_res = await session.execute(auth_stmt)
                author = auth_res.scalar_one_or_none()
                if not author:
                    continue

                # Check if relation already exists
                rel_stmt = select(AuthorArticle).where(
                    AuthorArticle.id_sinta == author.id_sinta,
                    AuthorArticle.id_article == article.id_article,
                )
                rel_res = await session.execute(rel_stmt)
                if not rel_res.scalar_one_or_none():
                    session.add(
                        AuthorArticle(
                            id_sinta=author.id_sinta,
                            id_article=article.id_article,
                        )
                    )
                    count_linked += 1

            await session.commit()

        await self._log(job_db_id, job_id, f"Linked {count_linked} author-article relations.")

    async def _save_authors(
        self,
        job_id: str,
        job_db_id: int,
        authors_data: List[Dict[str, Any]],
    ) -> int:
        """
        Update Author rows with OpenAlex bibliometric stats.
        Matches by strip_titles()-normalized fullname.
        Only updates existing authors; does NOT create new stub rows.

        Returns:
            Number of author rows updated.
        """
        count_updated = 0

        async with async_session_maker() as session:
            for item in authors_data:
                raw_name = item.get("display_name")
                if not raw_name:
                    continue

                normalized = strip_titles(raw_name)

                stmt = select(Author).where(Author.fullname == normalized)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.s_article_gscholar   = item.get("works_count")
                    existing.s_citation_gscholar  = item.get("cited_by_count")
                    existing.s_hindex_gscholar    = item.get("h_index")
                    existing.s_i10_index_gscholar = item.get("i10_index")
                    count_updated += 1

            await session.commit()

        await self._log(job_db_id, job_id, f"Updated {count_updated} authors from OpenAlex.")
        return count_updated

    # -----------------------------------------------------------------------
    # Job lifecycle helpers — each uses its own short session
    # -----------------------------------------------------------------------

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
                message=f"Job finished successfully — {total_records} records.",
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
        """
        Append a log entry using its own short-lived session.
        Uses job_db_id (integer PK) directly — no UUID re-query needed.
        Also emits to the Python logger for stdout visibility.
        """
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
