import logging
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.job import ScrapingJob, JobStatus, ScrapingLog, LogLevel, JobSource
from app.models.work import Work, AuthorWork
from app.models.author import Author
from app.services.scraper.crossref import CrossrefScraper
from app.services.scraper.openalex import OpenAlexScraper
from app.services.job_service import JobService
from app.core.config import settings

logger = logging.getLogger(__name__)

class ScrapingService:
    """
    Orchestrates scraping jobs:
    1. Fetches job details
    2. Runs selected scrapers (Crossref/OpenAlex)
    3. Processes and saves results to DB (Upsert)
    4. Updates job status and logs
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.job_service = JobService(db)

    async def run_scraping_job(self, job_id: str):
        """
        Execute the scraping job.
        This should be called from a background task.
        
        Args:
            job_id: UUID of the job to run
        """
        job = await self.job_service.start_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found or could not be started")
            return

        try:
            params = job.parameters or {}
            source = job.source
            
            # Fetch authors from database
            await self._log(job.id, "Fetching authors from database...")
            stmt = select(Author.fullname).where(Author.fullname.is_not(None))
            result = await self.db.execute(stmt)
            db_authors = [row[0] for row in result.all()]
            
            if db_authors:
                authors = db_authors
                await self._log(job.id, f"Found {len(authors)} authors in database.")
            else:
                # Fallback if DB is empty
                authors = params.get("authors") or settings.default_authors
                await self._log(job.id, f"No authors found in DB. Using {len(authors)} authors from parameters/defaults.", level=LogLevel.WARNING)

            year_start = params.get("year_start")
            year_end = params.get("year_end")
            filter_unikom = params.get("filter_unikom")

            full_results = []
            
            # --- Crossref Scraping ---
            if source in [JobSource.CROSSREF, JobSource.BOTH]:
                await self._log(job.id, "Starting Crossref scraping...")
                crossref_scraper = CrossrefScraper(filter_unikom=filter_unikom)
                
                crossref_results = await crossref_scraper.scrape(
                    authors=authors,
                    year_start=year_start,
                    year_end=year_end,
                    on_progress=lambda a, p, t: asyncio.create_task(
                        self._log(job.id, f"Crossref: Processing {a} ({p}/{t})")
                    )
                )
                full_results.extend(crossref_results)
                await self._log(job.id, f"Crossref finished. Found {len(crossref_results)} works.")

            # --- OpenAlex Scraping ---
            if source in [JobSource.OPENALEX, JobSource.BOTH]:
                await self._log(job.id, "Starting OpenAlex scraping...")
                openalex_scraper = OpenAlexScraper()
                
                # Note: OpenAlex scraper implementation might need adjustment to match list-based input
                # For now assuming it has a similar interface or we iterate
                openalex_results = []
                total_authors = len(authors)
                for idx, author in enumerate(authors):
                    # Log progress periodically
                    if idx % 5 == 0:
                        await self._log(job.id, f"OpenAlex: Processing {author} ({idx+1}/{total_authors})")
                        
                    res = await openalex_scraper.fetch_author_data(author)
                    if res:
                        openalex_results.append(res)
                
                # OpenAlex results are Authors, not Works directly. 
                # We need to save Authors separately.
                await self._save_authors(job.id, openalex_results)
                await self._log(job.id, f"OpenAlex finished. Found {len(openalex_results)} authors.")

            # --- Save Works Results ---
            if full_results:
                await self._save_works(job.id, full_results)

            total_records = len(full_results) # Works count is the primary metric for "records" usually
            
            await self.job_service.finish_job(job_id, total_records)

        except Exception as e:
            logger.exception(f"Job {job_id} failed with error: {e}")
            await self.job_service.fail_job(job_id, str(e))

    async def _save_works(self, job_uuid: str, works_data: List[Dict[str, Any]]):
        """
        Save Work records to database using UPSERT strategy.
        """
        job = await self.job_service.get_job_by_uuid(job_uuid)
        job_id = job.id # DB ID for logs

        count_new = 0
        count_updated = 0

        # Save Works
        new_works = []
        for item in works_data:
            doi = item.get("doi")
            if not doi:
                continue

            # ID Generation Strategy: "doi_" + DOI
            id_work = f"doi_{doi}"
            
            # Check existing Work
            stmt = select(Work).where(Work.id_work == id_work)
            result = await self.db.execute(stmt)
            existing_work = result.scalar_one_or_none()

            # Map fields
            work_dict = {
                "id_work": id_work,
                "doi": doi,
                "title": item.get("title"),
                "abstract": item.get("abstract"),
                "authors": item.get("authors"),
                "author_query": item.get("author_query"),
                "container_title": item.get("container_title"),
                "short_container_title": item.get("short_container_title"),
                "publisher": item.get("publisher"),
                "issue": item.get("issue"),
                "volume": item.get("volume"),
                "page": item.get("page"),
                "published": str(item.get("published_date")) if item.get("published_date") else None,
                "type": item.get("type"),
                "source": item.get("source"),
                "pdf_link": item.get("pdf_link"),
                "all_links": "; ".join(item.get("all_links", [])),
                "score": item.get("score"),
                "issn": "; ".join(item.get("issn", [])),
                "issn_type": "; ".join(item.get("issn_type", [])) if isinstance(item.get("issn_type"), list) else str(item.get("issn_type")),
                "url": item.get("url"),
                "indexed_date_parts": item.get("indexed_date_parts"),
            }

            if existing_work:
                # Update existing
                for key, value in work_dict.items():
                    setattr(existing_work, key, value)
                count_updated += 1
            else:
                # Create new
                new_work = Work(**work_dict)
                self.db.add(new_work)
                count_new += 1
                new_works.append(new_work)
        
        await self.db.flush() # Ensure works are persisted to get IDs (though we set string IDs manually)

        # --- Handle Author-Work Relations ---
        # For each work, we need to link it to the author found in the query.
        # Note: We rely on 'author_query' field in work data to know which author triggered this result.
        
        count_relations = 0
        for item in works_data:
            doi = item.get("doi")
            author_query_name = item.get("author_query")
            if not doi or not author_query_name:
                continue
            
            id_work = f"doi_{doi}" # Reconstruct ID
            
            # Find the author by name (handling normalized names could be tricky, assume exact/close match from query)
            # In our scraping flow, 'author_query' comes from the loop over input authors.
            
            # Try to match author by fullname (Legacy) or name (Scraper)
            # We use ILIKE for case-insensitive matching if acceptable, or just exact match
            stmt = select(Author).where(Author.fullname == author_query_name)
            result = await self.db.execute(stmt)
            author = result.scalar_one_or_none()
            
            if not author:
                # If author doesn't exist yet (unlikely if we just inserted them, 
                # but Crossref scraping doesn't insert authors automatically like OpenAlex might),
                # we might need to create a placeholder author or skip.
                # For now, let's log and skip to avoid errors.
                # A better approach: The scrape job should ensure authors exist first?
                # Actually, our current flow scrapes Works then Authors. 
                # If we only scraped Crossref, Author might not exist in DB yet if it wasn't in OpenAlex or legacy.
                
                # Check if we should create a stub author
                stmt_stub = select(Author).where(Author.fullname == author_query_name)
                res_stub = await self.db.execute(stmt_stub)
                if not res_stub.scalar_one_or_none():
                     stub_author = Author(fullname=author_query_name, name=author_query_name)
                     self.db.add(stub_author)
                     await self.db.flush()
                     author = stub_author
                else:
                     continue # Should have been found above

            if author:
                # Check if relation exists
                stmt_rel = select(AuthorWork).where(
                    and_(
                        AuthorWork.id_author == author.id_author,
                        AuthorWork.id_work == id_work
                    )
                )
                result_rel = await self.db.execute(stmt_rel)
                existing_rel = result_rel.scalar_one_or_none()
                
                if not existing_rel:
                    new_rel = AuthorWork(
                        id_author=author.id_author,
                        id_work=id_work,
                        author_query=author_query_name,
                        is_corresponding=False # Default
                    )
                    self.db.add(new_rel)
                    count_relations += 1

        await self.db.commit()
        await self._log(job_uuid, f"Saved works: {count_new} new, {count_updated} updated. Linked {count_relations} author-work relations.")

    async def _save_authors(self, job_uuid: str, authors_data: List[Dict[str, Any]]):
        """
        Save Author records from OpenAlex.
        """
        count_new = 0
        count_updated = 0
        
        for item in authors_data:
            openalex_id = item.get("id") # OpenAlex ID
            if not openalex_id:
                continue
            
            # Check existing by OpenAlex ID
            stmt = select(Author).where(Author.openalex_id == openalex_id)
            result = await self.db.execute(stmt)
            existing_author = result.scalar_one_or_none()
            
            # If not found by OpenAlex ID, try by name? 
            # Or just create new. The legacy DB has no OpenAlex ID, so we might duplicate if we don't match by name.
            # Matching by name is risky but necessary for merging.
            if not existing_author:
                name = item.get("display_name")
                stmt = select(Author).where(Author.fullname == name)
                result = await self.db.execute(stmt)
                existing_author = result.scalar_one_or_none()

            author_dict = {
                "openalex_id": openalex_id,
                "name": item.get("display_name"),
                "works_count": item.get("works_count"),
                "cited_by_count": item.get("cited_by_count"),
                "h_index": item.get("h_index"),
                "i10_index": item.get("i10_index"),
                "relevance_score": item.get("relevance_score"),
                "orcid": item.get("orcid"),
                "two_yr_mean_citedness": item.get("2yr_mean_citedness") # Field might need check
            }
            
            if existing_author:
                # Update
                for key, value in author_dict.items():
                    setattr(existing_author, key, value)
                count_updated += 1
            else:
                # Create
                # Map name to fullname for legacy compatibility if new
                author_dict["fullname"] = author_dict["name"] 
                new_author = Author(**author_dict)
                self.db.add(new_author)
                count_new += 1
                
        await self.db.commit()
        await self._log(job_uuid, f"Saved authors: {count_new} new, {count_updated} updated.")

    async def _log(self, job_uuid: str, message: str, level: LogLevel = LogLevel.INFO):
        """Helper to add log to job"""
        job = await self.job_service.get_job_by_uuid(job_uuid)
        if job:
            await self.job_service.add_log(job.id, level, message)
            logger.info(f"[Job {job_uuid}] {message}")
