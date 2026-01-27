"""
Crossref API Scraper.
Adapted from Reference/jurnal/crossref/main.js

Preserves logic:
- Pagination with offset and rows parameters
- Query by author name with year filter
- Exact author matching with name normalization
- Optional UNIKOM affiliation filter
- All 22+ fields extraction
"""

import logging
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


class CrossrefScraper(BaseScraper):
    """
    Scraper for Crossref Works API.
    
    Adapted from Reference/jurnal/crossref/main.js
    Key features preserved:
    - Pagination: offset-based with configurable rows per request
    - Filtering: by author name and publication year
    - Matching: exact author name matching after normalization
    - Output: 22+ fields matching original CSV output
    """

    def __init__(
        self,
        rows_per_request: int = None,
        max_offset: int = None,
        request_delay: float = None,
        max_retries: int = None,
        filter_unikom: bool = None,
    ):
        """
        Initialize Crossref scraper.
        
        Args:
            rows_per_request: Number of results per API request (default: 100)
            max_offset: Maximum offset for pagination (default: 10000)
            request_delay: Delay between requests in seconds (default: 0.5)
            max_retries: Maximum retry attempts (default: 3)
            filter_unikom: Filter for UNIKOM affiliation (default: False)
        """
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
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all works for an author in a specific year.
        
        Adapted from fetchWorksByAuthorYear() in main.js
        
        Args:
            author_name: Author name to search
            year: Publication year to filter
            on_progress: Optional callback for progress updates
            
        Returns:
            List of work items from Crossref API
        """
        works = []
        offset = 0
        
        while offset < self.max_offset:
            # Build URL with query parameters
            url = (
                f"{self.base_url}/works"
                f"?query.author={quote(author_name)}"
                f"&filter=from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
                f"&rows={self.rows_per_request}&offset={offset}"
            )
            
            try:
                data = await self._request_with_retry(url)
                message = data.get("message", {})
                items = message.get("items", [])
                
                if not items:
                    logger.debug(f"No more items for {author_name} in {year} at offset {offset}")
                    break
                
                works.extend(items)
                
                total_results = message.get("total-results", 0)
                logger.info(
                    f"Fetched {len(items)} works for {author_name} ({year}), "
                    f"offset {offset}, total available: {total_results}"
                )
                
                if on_progress:
                    on_progress(len(works))
                
                offset += self.rows_per_request
                
                # Stop if we've fetched all available results
                if offset >= total_results:
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching works for {author_name} ({year}): {e}")
                break
        
        return works

    def is_exact_author_match(self, work: Dict[str, Any], query_author: str) -> bool:
        """
        Check if work contains exact author match.
        
        Adapted from isExactAuthorMatch() in main.js
        
        Args:
            work: Work item from Crossref API
            query_author: Author name being searched
            
        Returns:
            True if work has matching author
        """
        target = normalize_name(query_author)
        authors = work.get("author", [])
        
        for author in authors:
            full_name = extract_author_full_name(author)
            if normalize_name(full_name) == target:
                return True
        
        return False

    def is_exact_author_from_unikom(self, work: Dict[str, Any], query_author: str) -> bool:
        """
        Check if work contains exact author match with UNIKOM affiliation.
        
        Adapted from isExactAuthorFromUNIKOM() in main.js
        
        Args:
            work: Work item from Crossref API
            query_author: Author name being searched
            
        Returns:
            True if work has matching author with UNIKOM affiliation
        """
        target = normalize_name(query_author)
        authors = work.get("author", [])
        
        for author in authors:
            full_name = extract_author_full_name(author)
            if normalize_name(full_name) != target:
                continue
            
            if is_unikom_affiliated(author):
                return True
        
        return False

    def filter_works(
        self,
        works: List[Dict[str, Any]],
        query_author: str,
    ) -> List[Dict[str, Any]]:
        """
        Filter works by author match criteria.
        
        Args:
            works: List of work items
            query_author: Author name being searched
            
        Returns:
            Filtered list of works
        """
        filtered = []
        
        for work in works:
            if self.filter_unikom:
                match = self.is_exact_author_from_unikom(work, query_author)
            else:
                match = self.is_exact_author_match(work, query_author)
            
            if match:
                filtered.append(work)
        
        return filtered

    def extract_work_data(self, work: Dict[str, Any], query_author: str) -> Dict[str, Any]:
        """
        Extract structured data from a Crossref work item.
        
        Adapted from workToCSVRow() in main.js - extracts all 22+ fields
        
        Args:
            work: Work item from Crossref API
            query_author: Author name used in query
            
        Returns:
            Dictionary with extracted fields
        """
        # Extract authors string
        authors = work.get("author", [])
        authors_str = "; ".join(
            extract_author_full_name(a) for a in authors
        )
        
        # Extract container titles
        container_title = (work.get("container-title") or [""])[0]
        short_container_title = (work.get("short-container-title") or [""])[0]
        
        # Extract published date
        published_print = work.get("published-print", {})
        published_online = work.get("published-online", {})
        date_parts = (
            published_print.get("date-parts") or 
            published_online.get("date-parts") or 
            []
        )
        published_date_str = parse_date_parts(date_parts)
        
        # Parse to date object if valid
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
        
        # Extract indexed datetime
        indexed = work.get("indexed", {})
        indexed_datetime_str = indexed.get("date-time", "")
        indexed_date_parts = indexed.get("date-parts", [])
        indexed_date_parts_str = "; ".join(
            "-".join(str(p) for p in parts) for parts in indexed_date_parts
        )
        
        # Parse indexed datetime
        indexed_at = None
        if indexed_datetime_str:
            try:
                indexed_at = datetime.fromisoformat(indexed_datetime_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        # Extract links
        links = work.get("link", [])
        pdf_link = ""
        all_links = []
        for link in links:
            url = link.get("URL", "")
            all_links.append(url)
            if link.get("content-type") == "application/pdf":
                pdf_link = url
        
        # Extract ISSNs
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
            "all_authors": authors,  # Raw author data for storage
        }

    async def scrape(
        self,
        authors: List[str],
        year_start: int = None,
        year_end: int = None,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method - fetch works for multiple authors across years.
        
        Args:
            authors: List of author names to search
            year_start: Start year (inclusive)
            year_end: End year (inclusive)
            on_progress: Optional callback(author, processed, total)
            
        Returns:
            List of extracted work data
        """
        year_start = year_start or settings.year_start
        year_end = year_end or settings.year_end
        
        all_results = []
        total_authors = len(authors)
        
        for idx, author in enumerate(authors):
            logger.info(f"Processing author {idx + 1}/{total_authors}: {author}")
            
            for year in range(year_start, year_end + 1):
                try:
                    works = await self.fetch_works_by_author_year(author, year)
                    filtered = self.filter_works(works, author)
                    
                    for work in filtered:
                        data = self.extract_work_data(work, author)
                        all_results.append(data)
                    
                    logger.info(
                        f"Author {author}, year {year}: "
                        f"fetched {len(works)}, matched {len(filtered)}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing {author} for year {year}: {e}")
            
            if on_progress:
                on_progress(author, idx + 1, total_authors)
        
        logger.info(f"Scraping complete: {len(all_results)} total works extracted")
        return all_results
