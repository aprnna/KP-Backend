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
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.database import async_session_maker
from app.models.job import ScrapingJob, JobStatus, JobSource
from app.models.sinta_article import SintaArticle
from app.models.sinta_author import SintaAuthor
from app.services.scraper.sinta_article import SintaArticleScraper
from app.services.scraper.sinta_author import SintaAuthorScraper
from app.services.scraper.crossref_article import CrossrefScraper


logger = logging.getLogger(__name__)

ARTICLE_BATCH_SIZE = 200
MAX_JOB_LOG_ENTRIES = 5000
SOURCE_PRIORITY = {"rama": 1, "googlescholar": 2, "garuda": 3, "scopus": 4, "crossref": 5}


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

PROGRESS_UPDATE_INTERVAL = 5  

@dataclass
class ProgressTracker:
    """Track scraping progress with throttled database updates."""
    total: int = 0
    processed: int = 0
    last_db_update: float = field(default_factory=time.monotonic)
    
    def should_update_db(self) -> bool:
        """Check if enough time has passed for a DB update."""
        elapsed = time.monotonic() - self.last_db_update
        return elapsed >= PROGRESS_UPDATE_INTERVAL
    
    def mark_db_updated(self) -> None:
        """Mark that DB was just updated."""
        self.last_db_update = time.monotonic()
# ---------------------------------------------------------------------------
# ScrapingService
# ---------------------------------------------------------------------------

class ScrapingService:
    def __init__(self):
        """Initialize ScrapingService with progress trackers."""
        self._progress_trackers: Dict[int, ProgressTracker] = {}
        self._job_log_buffers: Dict[int, List[Dict[str, Any]]] = {}

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
            
            # Phase 1: SINTA Author Scraping
            if source in (JobSource.SINTA_AUTHORS, JobSource.BOTH):
                sinta_ids = await self._scrape_authors_phase(job_id, job_db_id, metrics)

            # Phase 2: SINTA Article Scraping
            if source in (JobSource.SINTA_ARTICLES, JobSource.BOTH):
                await self._scrape_articles_phase(job_id, job_db_id, metrics, sinta_ids)

            # Finalize once, with source-aware totals.
            if source == JobSource.SINTA_AUTHORS:
                final_total_records = metrics.total_authors_saved or metrics.total_sinta_ids
            else:
                final_total_records = metrics.total_articles

            await self._finish_job(job_id, job_db_id, final_total_records)

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

    async def _scrape_authors_phase(self, job_id: str, job_db_id: int, metrics: JobMetrics) -> List[int]:
        """Handles the author scraping phase."""
        await self._log(job_db_id, job_id, "Starting SINTA author profile scraping natively via Affiliation…")

        async with SintaAuthorScraper() as scraper:
            # sinta_ids=None triggers the scraper to fetch the full UNIKOM affiliation list first
            author_results = await scraper.scrape(
                sinta_ids=None,
                job_id=job_id,
                on_progress=lambda sid, p, t: asyncio.create_task(
                    self._on_scraping_progress(job_db_id, job_id, sid, p, t)
                ),
            )

        saved_authors = await self._save_authors(job_id, job_db_id, author_results)
        metrics.total_authors_saved = saved_authors
        
        # Extract SINTA IDs for the article scraper
        sinta_ids = [a.get("id_sinta") for a in author_results if a.get("id_sinta")]
        metrics.total_sinta_ids = len(sinta_ids)

        await self._log(
            job_db_id, job_id,
            f"Author scraping done: {saved_authors}/{len(author_results)} saved.",
        )
        return sinta_ids

    async def _scrape_articles_phase(self, job_id: str, job_db_id: int, metrics: JobMetrics, sinta_ids: List[int]) -> None:
        """Handles the article scraping and Crossref enrichment phase."""
        # If we didn't just scrape authors, we need to load the list of SINTA IDs.
        if not sinta_ids:
            sinta_ids = await self._resolve_sinta_ids(job_id, job_db_id)
            metrics.total_sinta_ids = len(sinta_ids)

        await self._log(job_db_id, job_id, f"Starting SINTA article scraping for {len(sinta_ids)} authors…")

        async with SintaArticleScraper() as scraper:
            article_results = await scraper.scrape(
                sinta_ids=sinta_ids,
                job_id=job_id,
                on_progress=lambda sid, p, t: asyncio.create_task(
                    self._on_scraping_progress(job_db_id, job_id, sid, p, t)
                ),
            )

        await self._log(job_db_id, job_id, f"Enriching {len(article_results)} articles with Crossref API…")
        async with CrossrefScraper() as crossref_scraper:
            await crossref_scraper.enrich_articles(article_results)

        total_saved = await self._save_articles_batched(job_id, job_db_id, article_results)
        metrics.total_articles = total_saved
        await self._log(
            job_db_id, job_id,
            f"Article scraping done: {len(article_results)} found, {total_saved} saved.",
        )

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
            job.run_logs = []
            await session.commit()
            self._job_log_buffers[job.id] = []
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
                    total_records=total_records,   
                    processed_records=total_records,
                    run_logs=self._job_log_buffers.get(job_db_id, []),
                )
            )
            await session.commit()

        # Prevent tracker buildup for long-running workers.
        self._progress_trackers.pop(job_db_id, None)
        self._job_log_buffers.pop(job_db_id, None)

    async def _update_job_progress(self, job_db_id: int, total: int, processed: int) -> None:
        """Update job progress in DB (throttled)."""
        async with async_session_maker() as session:
            await session.execute(
                update(ScrapingJob)
                .where(ScrapingJob.id == job_db_id)
                .values(total_records=total, processed_records=processed)
            )
            await session.commit()

    async def _on_scraping_progress(self, job_db_id: int, job_id: str, sinta_id: int, processed: int, total: int) -> None:
        """Handle progress dengan throttling."""
        is_new_tracker = job_db_id not in self._progress_trackers
        if is_new_tracker:
            self._progress_trackers[job_db_id] = ProgressTracker(total=total, processed=processed)
        
        tracker = self._progress_trackers[job_db_id]
        tracker.total = total
        tracker.processed = processed
        
        if is_new_tracker or tracker.should_update_db():
            await self._update_job_progress(job_db_id, total, processed)
            tracker.mark_db_updated()
        
        self._append_job_log(job_db_id, logging.INFO, f"Progress: {sinta_id} ({processed}/{total})")
        logger.info("scraping_progress", extra={"job_id": job_id, "sinta_id": sinta_id, "processed": processed, "total": total})

    async def _fail_job(self, job_id: str, job_db_id: Optional[int], error: str) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(ScrapingJob)
                .where(ScrapingJob.job_id == job_id)
                .values(
                    status=JobStatus.FAILED,
                    finished_at=datetime.utcnow(),
                    error_message=error,
                    run_logs=self._job_log_buffers.get(job_db_id, []),
                )
            )
            await session.commit()

        if job_db_id is not None:
            self._progress_trackers.pop(job_db_id, None)
            self._job_log_buffers.pop(job_db_id, None)

    async def _log(
        self,
        job_db_id: int,
        job_id: str,
        message: str,
        level: int = logging.INFO,
    ) -> None:
        """Emit application logs and collect per-job logs for final DB persistence."""
        self._append_job_log(job_db_id, level, message)
        logger.log(level, message, extra={"job_id": job_id, "job_db_id": job_db_id})

    def _append_job_log(self, job_db_id: int, level: int, message: str) -> None:
        """Append log entry to in-memory per-job buffer with size guard."""
        if job_db_id not in self._job_log_buffers:
            self._job_log_buffers[job_db_id] = []

        logs = self._job_log_buffers[job_db_id]
        if len(logs) >= MAX_JOB_LOG_ENTRIES:
            if logs and logs[-1].get("message") != "Log truncated due to max entries limit.":
                logs.append(
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "level": "WARNING",
                        "message": "Log truncated due to max entries limit.",
                    }
                )
            return

        logs.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "level": logging.getLevelName(level),
                "message": message,
            }
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
        Duplicate (id_sinta, article_title) rows from different views are merged.
        """
        total_saved = 0
        buffer: List[Dict[str, Any]] = []
        merged_items: Dict[tuple[int, str], Dict[str, Any]] = {}

        for item in articles_data:
            row = {k: v for k, v in item.items() if k != "profile_url"}

            key = self._article_merge_key(row)
            if key is None:
                # Keep rows with missing merge keys untouched.
                buffer.append(row)
            elif key in merged_items:
                self._merge_article_data(merged_items[key], row)
            else:
                merged_items[key] = dict(row)

            if len(buffer) + len(merged_items) >= ARTICLE_BATCH_SIZE:
                if merged_items:
                    buffer.extend(merged_items.values())
                    merged_items.clear()
            if len(buffer) >= ARTICLE_BATCH_SIZE:
                total_saved += await self._flush_article_batch(buffer)
                buffer.clear()

        if merged_items:
            buffer.extend(merged_items.values())

        if buffer:
            total_saved += await self._flush_article_batch(buffer)

        return total_saved

    @staticmethod
    def _article_merge_key(row: Dict[str, Any]) -> Optional[tuple[int, str]]:
        """Build merge key for cross-view article deduplication."""
        id_sinta = row.get("id_sinta")
        title = row.get("article_title")
        if id_sinta is None or not title:
            return None
        normalized_title = re.sub(r"\s+", " ", str(title).strip().lower())
        if not normalized_title:
            return None
        return int(id_sinta), normalized_title

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return value is None or (isinstance(value, str) and value.strip() == "")

    @staticmethod
    def _split_sources(value: Any) -> List[str]:
        """Split persisted source label into normalized source tokens."""
        if value is None:
            return []
        text = str(value).strip().lower()
        if not text:
            return []
        tokens = re.split(r"\s*(?:,|\||/|&|dan)\s*", text)
        valid_tokens: List[str] = []
        for token in tokens:
            if token in SOURCE_PRIORITY and token not in valid_tokens:
                valid_tokens.append(token)
        return valid_tokens

    def _merge_article_data(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        """
        Merge article data from different SINTA views.

        Rules:
        - Fill only fields that are currently null/empty.
        - Prefer `quartile` from scopus view.
        - Prefer `sinta_rank` from garuda view.
        - Keep the highest-priority source label.
        """
        incoming_source = (incoming.get("source") or "").strip().lower()

        # 1. Merge sources prioritizing specific providers
        base["source"] = self._merge_sources(base.get("source"), incoming_source)
        
        # 2. Fill generic scalar fields
        self._merge_generic_fields(base, incoming)

        # 3. Apply business rules for authoritative domains (e.g., Scopus, Garuda)
        self._apply_source_specific_rules(base, incoming, incoming_source)

    def _merge_sources(self, base_source: Any, incoming_source: str) -> str:
        """Merge and prioritize source labels up to a safe database column limit."""
        merged_sources = self._split_sources(base_source)
        
        if incoming_source in SOURCE_PRIORITY and incoming_source not in merged_sources:
            merged_sources.append(incoming_source)

        if merged_sources:
            merged_sources = sorted(
                merged_sources,
                key=lambda src: SOURCE_PRIORITY.get(src, 0),
                reverse=True,
            )
            # Keep max two highest-priority sources to stay compact, 
            # and fallback to 1 if taking two exceeds VARCHAR(20)
            result_source = ",".join(merged_sources[:2])
            if len(result_source) > 20:
                result_source = merged_sources[0]
            return result_source
            
        return base_source or ""

    def _merge_generic_fields(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        """Merge generic string/numeric fields if currently empty."""
        fill_fields = [
            "year", "cited", "url",
            "pdf_link", "raw_type", "issn", "issn_type",
            "indexed_date_time", "indexed_date_parts", "short_journal_title",
            "journal_title", "issue", "volume"
        ]
        for field_name in fill_fields:
            if self._is_empty(base.get(field_name)) and not self._is_empty(incoming.get(field_name)):
                base[field_name] = incoming.get(field_name)

        # Keep latest scrape timestamp.
        incoming_scraped_at = incoming.get("scraped_at")
        if incoming_scraped_at is not None:
            base["scraped_at"] = incoming_scraped_at

    def _apply_source_specific_rules(self, base: Dict[str, Any], incoming: Dict[str, Any], incoming_source: str) -> None:
        """Apply business rules where certain sources are authoritative for specific fields."""
        incoming_quartile = incoming.get("quartile")
        incoming_sinta_rank = incoming.get("sinta_rank")
        incoming_publisher = incoming.get("publisher")
        incoming_authors = incoming.get("authors")
        incoming_doi = incoming.get("doi")

        # Scopus is authoritative for quartile.
        if incoming_source == "scopus":
            if not self._is_empty(incoming_quartile):
                base["quartile"] = incoming_quartile
        elif self._is_empty(base.get("quartile")) and not self._is_empty(incoming_quartile):
            base["quartile"] = incoming_quartile

        # Garuda is authoritative for SINTA rank.
        if incoming_source == "garuda":
            if incoming_sinta_rank is not None:
                base["sinta_rank"] = incoming_sinta_rank
            if not self._is_empty(incoming_doi):
                base["doi"] = incoming_doi
        elif base.get("sinta_rank") is None and incoming_sinta_rank is not None:
            base["sinta_rank"] = incoming_sinta_rank
            if self._is_empty(base.get("doi")) and not self._is_empty(incoming_doi):
                base["doi"] = incoming_doi
        
        # Google Scholar is authoritative for publisher information.
        if incoming_source == "googlescholar":
            if not self._is_empty(incoming_publisher):
                base["publisher"] = incoming_publisher
            if not self._is_empty(incoming_authors):
                base["authors"] = incoming_authors
        else:
            if self._is_empty(base.get("publisher")) and not self._is_empty(incoming_publisher):
                base["publisher"] = incoming_publisher
            if self._is_empty(base.get("authors")) and not self._is_empty(incoming_authors):
                base["authors"] = incoming_authors

        # Fallback DOI fill for non-garuda sources.
        if self._is_empty(base.get("doi")) and not self._is_empty(incoming_doi):
            base["doi"] = incoming_doi

    async def _flush_article_batch(self, batch: List[Dict[str, Any]]) -> int:
        """INSERT or UPDATE a single batch of articles in the scraping DB."""
        if not batch:
            return 0

        async with async_session_maker() as session:
            keyed_rows: Dict[tuple[int, str], Dict[str, Any]] = {}
            keyless_rows: List[Dict[str, Any]] = []
            for row in batch:
                key = self._article_merge_key(row)
                if key is None:
                    keyless_rows.append(row)
                    continue
                if key in keyed_rows:
                    self._merge_article_data(keyed_rows[key], row)
                else:
                    keyed_rows[key] = dict(row)

            existing_by_key: Dict[tuple[int, str], SintaArticle] = {}
            if keyed_rows:
                id_values = list({key[0] for key in keyed_rows.keys()})
                title_values = [row["article_title"] for row in keyed_rows.values() if row.get("article_title")]
                if id_values and title_values:
                    existing_result = await session.execute(
                        select(SintaArticle).where(
                            SintaArticle.id_sinta.in_(id_values),
                            SintaArticle.article_title.in_(title_values),
                        )
                    )
                    for existing in existing_result.scalars().all():
                        existing_key = self._article_merge_key(
                            {"id_sinta": existing.id_sinta, "article_title": existing.article_title}
                        )
                        if existing_key is not None and existing_key not in existing_by_key:
                            existing_by_key[existing_key] = existing

            to_insert: List[SintaArticle] = []
            written = 0

            for key, incoming in keyed_rows.items():
                existing = existing_by_key.get(key)
                if existing is None:
                    to_insert.append(SintaArticle(**incoming))
                    written += 1
                    continue

                base = {
                    "source": existing.source,
                    "authors": existing.authors,
                    "publisher": existing.publisher,
                    "year": existing.year,
                    "cited": existing.cited,
                    "doi": existing.doi,
                    "quartile": existing.quartile,
                    "sinta_rank": existing.sinta_rank,
                    "url": existing.url,
                    "scraped_at": existing.scraped_at,
                    "pdf_link": existing.pdf_link,
                    "raw_type": existing.raw_type,
                    "issn": existing.issn,
                    "issn_type": existing.issn_type,
                    "indexed_date_time": existing.indexed_date_time,
                    "indexed_date_parts": existing.indexed_date_parts,
                    "short_journal_title": existing.short_journal_title,
                    "journal_title": existing.journal_title,
                    "issue": existing.issue,
                    "volume": existing.volume,
                }
                self._merge_article_data(base, incoming)

                existing.source = base.get("source")
                existing.authors = base.get("authors")
                existing.publisher = base.get("publisher")
                existing.year = base.get("year")
                existing.cited = base.get("cited")
                existing.doi = base.get("doi")
                existing.quartile = base.get("quartile")
                existing.sinta_rank = base.get("sinta_rank")
                existing.url = base.get("url")
                existing.scraped_at = base.get("scraped_at")
                existing.pdf_link = base.get("pdf_link")
                existing.raw_type = base.get("raw_type")
                existing.issn = base.get("issn")
                existing.issn_type = base.get("issn_type")
                existing.indexed_date_time = base.get("indexed_date_time")
                existing.indexed_date_parts = base.get("indexed_date_parts")
                existing.short_journal_title = base.get("short_journal_title")
                existing.journal_title = base.get("journal_title")
                existing.issue = base.get("issue")
                existing.volume = base.get("volume")
                written += 1

            if keyless_rows:
                for row in keyless_rows:
                    to_insert.append(SintaArticle(**row))
                    written += 1

            if to_insert:
                session.add_all(to_insert)

            await session.commit()

        return written

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
            "id_sinta", "fullname", "major", "degree", "faculty",
            "sinta_score_overall", "sinta_score_3yr", "affil_score", "affil_score_3yr",
            "s_article_scopus", "s_citation_scopus", "s_cited_document_scopus", 
            "s_hindex_scopus", "s_i10_index_scopus", "s_gindex_scopus",
            "s_article_gscholar", "s_citation_gscholar", "s_cited_document_gscholar", 
            "s_hindex_gscholar", "s_i10_index_gscholar", "s_gindex_gscholar",
            "subject_research"
        ]

        clean_rows = []
        for item in authors_data:
            # Ensure mandatory fields are present in clean_rows
            row = {k: item.get(k, None) for k in all_keys}
            row["scraped_at"] = item.get("scraped_at", datetime.utcnow())
            clean_rows.append(row)

        async with async_session_maker() as session:
            stmt = mysql_insert(SintaAuthor).values(clean_rows)
            stmt = stmt.on_duplicate_key_update(
                fullname=stmt.inserted.fullname,
                major=stmt.inserted.major,
                degree=stmt.inserted.degree,
                faculty=stmt.inserted.faculty,
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
