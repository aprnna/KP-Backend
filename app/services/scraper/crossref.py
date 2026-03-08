"""
Crossref API Scraper.
Adapted from Reference/jurnal/crossref/main.js

Preserves logic:
- Pagination with offset and rows parameters
- Query by author name with year filter
- Exact author matching with name normalization
- Optional UNIKOM affiliation filter
- All 22+ fields extraction

Improvements:
- MAX_CONCURRENT_AUTHORS semaphore for controlled parallelism
- Pagination offset warning at 10 000 limit
- Structured log extras (job_id, author, source, duration_ms)
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Callable
from datetime import date, datetime
from urllib.parse import quote

from app.services.scraper.base import BaseScraper
from app.services.scraper.utils import (
    normalize_name,
    extract_author_full_name,
    is_unikom_affiliated,
    parse_date_parts,
)
from app.core.config import settings


logger = logging.getLogger(__name__)

# Maximum concurrent author queries.
# Prevents API overload while still parallelising I/O-bound work.
MAX_CONCURRENT_AUTHORS = 5

# Crossref hard offset limit: results beyond this are silently truncated.
CROSSREF_OFFSET_HARD_LIMIT = 10_000


class CrossrefScraper(BaseScraper):
    """
    Scraper for Crossref Works API.

    Adapted from Reference/jurnal/crossref/main.js
    Key features:
    - Offset-based pagination with configurable rows per request
    - Filtering by author name and publication year
    - Exact author name matching after normalization
    - Optional UNIKOM affiliation filter
    - Concurrent author processing via asyncio.Semaphore
    """

    def __init__(
        self,
        rows_per_request: int = None,
        max_offset: int = None,
        request_delay: float = None,
        max_retries: int = None,
        filter_unikom: bool = None,
    ):
        super().__init__(
            base_url=settings.crossref_base_url,
            request_delay=request_delay or settings.crossref_request_delay,
            max_retries=max_retries or settings.crossref_max_retries,
        )
        self.rows_per_request = rows_per_request or settings.crossref_rows_per_request
        self.max_offset = max_offset or settings.crossref_max_offset
        self.filter_unikom = filter_unikom if filter_unikom is not None else settings.filter_unikom

    async def fetch_works_by_author_year(
        self,
        author_name: str,
        year: int,
        job_id: str = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all works for an author in a specific year with pagination.

        Includes a safeguard warning when the Crossref 10 000-offset limit
        is approached, preventing silent data truncation.
        """
        works = []
        offset = 0

        while offset < self.max_offset:
            # --- Pagination offset safeguard ---
            if offset >= CROSSREF_OFFSET_HARD_LIMIT:
                logger.warning(
                    "crossref_offset_limit_reached",
                    extra={
                        "job_id": job_id,
                        "author": author_name,
                        "year": year,
                        "offset": offset,
                        "note": "Results may be truncated; Crossref hard limit is 10 000",
                    },
                )
                break

            url = (
                f"{self.base_url}/works"
                f"?query.author={quote(author_name)}"
                f"&filter=from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
                f"&rows={self.rows_per_request}&offset={offset}"
            )

            try:
                t0 = time.monotonic()
                data = await self._request_with_retry(url)
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                message = data.get("message", {})
                items = message.get("items", [])

                if not items:
                    break

                works.extend(items)

                total_results = message.get("total-results", 0)
                logger.debug(
                    "crossref_page_fetched",
                    extra={
                        "job_id": job_id,
                        "author": author_name,
                        "year": year,
                        "offset": offset,
                        "items": len(items),
                        "total_available": total_results,
                        "elapsed_ms": elapsed_ms,
                        "source": "crossref",
                    },
                )

                if on_progress:
                    on_progress(len(works))

                offset += self.rows_per_request

                if offset >= total_results:
                    break

            except Exception as e:
                logger.error(
                    "crossref_fetch_error",
                    extra={
                        "job_id": job_id,
                        "author": author_name,
                        "year": year,
                        "offset": offset,
                        "error": str(e),
                        "source": "crossref",
                    },
                )
                break

        return works

    # ------------------------------------------------------------------
    # Filtering helpers
    # ------------------------------------------------------------------

    def is_exact_author_match(self, work: Dict[str, Any], query_author: str) -> bool:
        """Return True if the work contains an exact normalized author match."""
        target = normalize_name(query_author)
        for author in work.get("author", []):
            if normalize_name(extract_author_full_name(author)) == target:
                return True
        return False

    def is_exact_author_from_unikom(self, work: Dict[str, Any], query_author: str) -> bool:
        """Return True if the work has a matching author with a UNIKOM affiliation."""
        target = normalize_name(query_author)
        for author in work.get("author", []):
            if normalize_name(extract_author_full_name(author)) != target:
                continue
            if is_unikom_affiliated(author):
                return True
        return False

    def filter_works(
        self,
        works: List[Dict[str, Any]],
        query_author: str,
    ) -> List[Dict[str, Any]]:
        """Filter works by author match criteria (with or without UNIKOM filter)."""
        filtered = []
        for work in works:
            match = (
                self.is_exact_author_from_unikom(work, query_author)
                if self.filter_unikom
                else self.is_exact_author_match(work, query_author)
            )
            if match:
                filtered.append(work)
        return filtered

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def extract_work_data(self, work: Dict[str, Any], query_author: str) -> Dict[str, Any]:
        """
        Extract structured data from a Crossref work item.
        Adapted from workToCSVRow() in main.js — extracts all 22+ fields.
        """
        authors = work.get("author", [])
        authors_str = "; ".join(extract_author_full_name(a) for a in authors)

        container_title = (work.get("container-title") or [""])[0]
        short_container_title = (work.get("short-container-title") or [""])[0]

        published_print = work.get("published-print", {})
        published_online = work.get("published-online", {})
        date_parts = (
            published_print.get("date-parts")
            or published_online.get("date-parts")
            or []
        )
        published_date_str = parse_date_parts(date_parts)

        published_date = None
        if published_date_str:
            try:
                parts = [int(p) for p in published_date_str.split("-")]
                if len(parts) >= 3:
                    published_date = date(parts[0], parts[1], parts[2])
                elif len(parts) == 2:
                    published_date = date(parts[0], parts[1], 1)
                elif len(parts) == 1:
                    published_date = date(parts[0], 1, 1)
            except (ValueError, IndexError):
                pass

        indexed = work.get("indexed", {})
        indexed_datetime_str = indexed.get("date-time", "")
        indexed_date_parts = indexed.get("date-parts", [])
        indexed_date_parts_str = "; ".join(
            "-".join(str(p) for p in parts) for parts in indexed_date_parts
        )

        indexed_at = None
        if indexed_datetime_str:
            try:
                indexed_at = datetime.fromisoformat(indexed_datetime_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        links = work.get("link", [])
        pdf_link = ""
        all_links = []
        for link in links:
            url = link.get("URL", "")
            all_links.append(url)
            if link.get("content-type") == "application/pdf":
                pdf_link = url

        issn_list = work.get("ISSN", [])
        issn_type_list = work.get("issn-type", [])

        return {
            "author_query": query_author,
            "doi": work.get("DOI", ""),
            "title": (work.get("title") or [""])[0],
            "authors": authors_str,
            "container_title": container_title,
            "short_container_title": short_container_title,
            "publisher": work.get("publisher", ""),
            "issue": work.get("issue", ""),
            "volume": work.get("volume", ""),
            "page": work.get("page", ""),
            "published_date": published_date,
            "type": work.get("type", ""),
            "source": work.get("source", ""),
            "pdf_link": pdf_link,
            "all_links": all_links,
            "abstract": work.get("abstract", ""),
            "score": work.get("score"),
            "issn": issn_list,
            "issn_type": issn_type_list,
            "indexed_at": indexed_at,
            "indexed_date_parts": indexed_date_parts_str,
            "url": work.get("URL", ""),
            "all_authors": authors,
        }

    # ------------------------------------------------------------------
    # Main scrape method — concurrent per-author with semaphore
    # ------------------------------------------------------------------

    async def scrape(
        self,
        authors: List[str],
        year_start: int = None,
        year_end: int = None,
        job_id: str = None,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method — fetch works for multiple authors across years.

        Uses asyncio.gather with a Semaphore (MAX_CONCURRENT_AUTHORS) to
        parallelise I/O-bound HTTP work without overloading the Crossref API.

        The semaphore wraps ONLY the HTTP scraping step; DB writes happen
        outside this method and are NOT wrapped by the semaphore.

        Returns:
            List of extracted work dicts, one item per matched publication.
        """
        year_start = year_start or settings.year_start
        year_end = year_end or settings.year_end

        total_authors = len(authors)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUTHORS)

        async def scrape_author(idx: int, author: str) -> List[Dict[str, Any]]:
            author_results: List[Dict[str, Any]] = []

            async with semaphore:
                t0 = time.monotonic()

                for year in range(year_start, year_end + 1):
                    try:
                        works = await self.fetch_works_by_author_year(
                            author, year, job_id=job_id
                        )
                        filtered = self.filter_works(works, author)

                        for work in filtered:
                            author_results.append(self.extract_work_data(work, author))

                        logger.debug(
                            "crossref_author_year_done",
                            extra={
                                "job_id": job_id,
                                "author": author,
                                "year": year,
                                "fetched": len(works),
                                "matched": len(filtered),
                                "source": "crossref",
                            },
                        )

                    except Exception as e:
                        logger.error(
                            "crossref_author_year_error",
                            extra={
                                "job_id": job_id,
                                "author": author,
                                "year": year,
                                "error": str(e),
                                "source": "crossref",
                            },
                        )

                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    "crossref_author_complete",
                    extra={
                        "job_id": job_id,
                        "author": author,
                        "articles_found": len(author_results),
                        "duration_ms": elapsed_ms,
                        "source": "crossref",
                    },
                )

            if on_progress:
                on_progress(author, idx + 1, total_authors)

            return author_results

        # Launch all authors concurrently (semaphore limits actual parallelism)
        tasks = [scrape_author(idx, author) for idx, author in enumerate(authors)]
        per_author_lists = await asyncio.gather(*tasks)

        all_results = [item for sub in per_author_lists for item in sub]

        logger.info(
            "crossref_scrape_complete",
            extra={
                "job_id": job_id,
                "total_authors": total_authors,
                "total_articles": len(all_results),
                "source": "crossref",
            },
        )

        return all_results
