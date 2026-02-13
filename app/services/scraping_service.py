import logging
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.job import ScrapingJob, JobStatus, ScrapingLog, LogLevel, JobSource
from app.models.article import Article, AuthorArticle
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
                await self._log(job.id, f"Crossref finished. Found {len(crossref_results)} articles.")

            # --- OpenAlex Scraping ---
            if source in [JobSource.OPENALEX, JobSource.BOTH]:
                await self._log(job.id, "Starting OpenAlex scraping...")
                openalex_scraper = OpenAlexScraper()
                
                openalex_results = []
                total_authors = len(authors)
                for idx, author in enumerate(authors):
                    # Log progress periodically
                    if idx % 5 == 0:
                        await self._log(job.id, f"OpenAlex: Processing {author} ({idx+1}/{total_authors})")
                        
                    res = await openalex_scraper.fetch_author_data(author)
                    if res:
                        openalex_results.append(res)
                
                await self._save_authors(job.id, openalex_results)
                await self._log(job.id, f"OpenAlex finished. Found {len(openalex_results)} authors.")

            # --- Save Article Results ---
            if full_results:
                await self._save_articles(job.id, full_results)

            total_records = len(full_results)
            
            await self.job_service.finish_job(job_id, total_records)

        except Exception as e:
            logger.exception(f"Job {job_id} failed with error: {e}")
            await self.job_service.fail_job(job_id, str(e))

    async def _save_articles(self, job_uuid: str, articles_data: List[Dict[str, Any]]):
        """
        Save Article records to database using UPSERT strategy.
        """
        job = await self.job_service.get_job_by_uuid(job_uuid)
        
        count_new = 0
        count_updated = 0

        # Save Articles
        for item in articles_data:
            doi = item.get("doi")
            # Using DOI as a proxy for identifying unique articles if id_article is not available from source
            # But the schema has id_article as primary key.
            # For now, let's assume we might need a way to map this.
            
            # Map fields to match the new Article model
            article_dict = {
                "doi": doi,
                "title": item.get("title"),
                "authors": item.get("authors"),
                "journal_title": item.get("container_title"),
                "short_journal_title": item.get("short_container_title"),
                "publisher": item.get("publisher"),
                "issue": item.get("issue"),
                "volume": item.get("volume"),
                "page": item.get("page"),
                "published": str(item.get("published_date")) if item.get("published_date") else None,
                "type": item.get("type"),
                "pdf_link": item.get("pdf_link"),
                "issn": "; ".join(item.get("issn", [])) if isinstance(item.get("issn"), list) else item.get("issn"),
                "issn_type": "; ".join(item.get("issn_type", [])) if isinstance(item.get("issn_type"), list) else str(item.get("issn_type")),
                "url": item.get("url"),
                "indexed_date_parts": str(item.get("indexed_date_parts")) if item.get("indexed_date_parts") else None,
            }

            # Search existing by DOI
            stmt = select(Article).where(Article.doi == doi) if doi else select(Article).where(Article.title == article_dict["title"])
            result = await self.db.execute(stmt)
            existing_article = result.scalar_one_or_none()

            if existing_article:
                for key, value in article_dict.items():
                    setattr(existing_article, key, value)
                count_updated += 1
            else:
                new_article = Article(**article_dict)
                self.db.add(new_article)
                count_new += 1
        
        await self.db.flush()

        # Handle Author-Article Relations
        count_relations = 0
        for item in articles_data:
            doi = item.get("doi")
            author_query_name = item.get("author_query")
            if not author_query_name:
                continue
            
            # Get Article ID
            stmt_art = select(Article).where(Article.doi == doi) if doi else select(Article).where(Article.title == item.get("title"))
            res_art = await self.db.execute(stmt_art)
            article = res_art.scalar_one_or_none()
            
            if not article:
                continue

            # Find author by fullname
            stmt_auth = select(Author).where(Author.fullname == author_query_name)
            res_auth = await self.db.execute(stmt_auth)
            author = res_auth.scalar_one_or_none()
            
            if not author:
                # Create stub author with id_sinta if available or generated
                # For now just use fullname
                author = Author(fullname=author_query_name)
                self.db.add(author)
                await self.db.flush()

            if author and article:
                # Check if relation exists
                stmt_rel = select(AuthorArticle).where(
                    and_(
                        AuthorArticle.id_sinta == author.id_sinta,
                        AuthorArticle.id_article == article.id_article
                    )
                )
                result_rel = await self.db.execute(stmt_rel)
                if not result_rel.scalar_one_or_none():
                    new_rel = AuthorArticle(
                        id_sinta=author.id_sinta,
                        id_article=article.id_article
                    )
                    self.db.add(new_rel)
                    count_relations += 1

        await self.db.commit()
        await self._log(job_uuid, f"Saved articles: {count_new} new, {count_updated} updated. Linked {count_relations} author-article relations.")

    async def _save_authors(self, job_uuid: str, authors_data: List[Dict[str, Any]]):
        """
        Save Author records from OpenAlex.
        """
        count_new = 0
        count_updated = 0
        
        for item in authors_data:
            name = item.get("display_name")
            if not name:
                continue
            
            # Match by name for merging
            stmt = select(Author).where(Author.fullname == name)
            result = await self.db.execute(stmt)
            existing_author = result.scalar_one_or_none()

            author_dict = {
                "fullname": name,
                "s_article_gscholar": item.get("works_count"), # Mapping works_count to something in new schema
                "s_citation_gscholar": item.get("cited_by_count"),
                "s_hindex_gscholar": item.get("h_index"),
                "s_i10_index_gscholar": item.get("i10_index"),
            }
            
            if existing_author:
                for key, value in author_dict.items():
                    setattr(existing_author, key, value)
                count_updated += 1
            else:
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
