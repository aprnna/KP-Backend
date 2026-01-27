"""
OpenAlex API Scraper.
Adapted from Reference/author/openalex/match-author-openalex.js

Preserves logic:
- Search by name only (ignoring affiliation for broader matching)
- Name normalization (stripping titles like Prof, Dr, S.T, etc.)
- Picking top result by relevance
- Extracting specific stats: h-index, i10-index, 2yr_mean_citedness
"""

import logging
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import quote

from app.services.scraper.base import BaseScraper
from app.services.scraper.utils import strip_titles
from app.core.config import settings

logger = logging.getLogger(__name__)

class OpenAlexScraper(BaseScraper):
    """
    Scraper for OpenAlex Authors API.
    
    Adapted from Reference/author/openalex/match-author-openalex.js
    """

    def __init__(self, request_delay: float = None, max_retries: int = None):
        super().__init__(
            base_url=settings.openalex_base_url,
            request_delay=request_delay or settings.openalex_request_delay,
            max_retries=max_retries or settings.openalex_max_retries,
        )

    async def search_author(self, name: str) -> List[Dict[str, Any]]:
        """
        Search for an author by name.
        
        Args:
            name: Author name (will be normalized)
            
        Returns:
            List of candidate author objects
        """
        clean_name = strip_titles(name)
        # JS logic: ?search={name}&per_page=10
        url = (
            f"{self.base_url}/authors"
            f"?search={quote(clean_name)}"
            f"&per_page=10"
        )
        
        try:
            data = await self._request_with_retry(url)
            return data.get("results", [])
        except Exception as e:
            logger.error(f"Error searching author {name}: {e}")
            return []

    def extract_author_data(
        self,
        author_result: Dict[str, Any],
        original_name: str = None,
    ) -> Dict[str, Any]:
        """
        Adapted from data extraction in match-author-openalex.js
        
        Args:
            author_result: Author result from OpenAlex API
            original_name: Original searched name
            
        Returns:
            Dictionary with extracted author data
        """
        stats = author_result.get("summary_stats", {})
        
        return {
            "original_name": original_name,
            "openalex_id": author_result.get("id", ""),
            "display_name": author_result.get("display_name", ""),
            "orcid": author_result.get("orcid"),
            "relevance_score": author_result.get("relevance_score"),
            "works_count": author_result.get("works_count", 0),
            "cited_by_count": author_result.get("cited_by_count", 0),
            "h_index": stats.get("h_index", 0),
            "i10_index": stats.get("i10_index", 0),
            "two_yr_mean_citedness": stats.get("2yr_mean_citedness", 0.0),
        }

    async def match_author(
        self,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find best matching author for a name.
        
        Returns the most relevant result (first result from search).
        
        Args:
            name: Author name to match
            
        Returns:
            Author data dictionary or None if not found
        """
        clean_name = strip_titles(name)
        logger.info(f"Matching author: {name} → {clean_name}")
        
        results = await self.search_author(clean_name)
        
        if not results:
            logger.warning(f"No OpenAlex match found for: {name}")
            return None
        
        # Take the most relevant result (first in list)
        best_match = results[0]
        data = self.extract_author_data(best_match, original_name=name)
        
        logger.info(f"Matched '{name}' to '{best_match.get('display_name')}'")
        return data

    async def scrape(
        self,
        author_names: List[str],
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method - match multiple authors.
        
        Args:
            author_names: List of author names to match
            on_progress: Optional callback(author, processed, total)
            
        Returns:
            List of matched author data
        """
        results = []
        total = len(author_names)
        
        for idx, name in enumerate(author_names):
            try:
                author_data = await self.match_author(name)
                
                if author_data:
                    results.append(author_data)
                else:
                    # Add entry for unmatched authors
                    results.append({
                        "original_name": name,
                        "openalex_id": None,
                        "display_name": None,
                        "orcid": None,
                        "relevance_score": None,
                        "works_count": 0,
                        "cited_by_count": 0,
                        "h_index": 0,
                        "i10_index": 0,
                        "two_yr_mean_citedness": 0.0,
                        "matched": False,
                    })
                    
            except Exception as e:
                logger.error(f"Error matching author '{name}': {e}")
                results.append({
                    "original_name": name,
                    "error": str(e),
                    "matched": False,
                })
            
            if on_progress:
                on_progress(name, idx + 1, total)
        
        matched_count = sum(1 for r in results if r.get("openalex_id"))
        logger.info(
            f"OpenAlex scraping complete: {matched_count}/{total} authors matched"
        )
        
        return results

    async def get_author_works(
        self,
        openalex_id: str,
        per_page: int = 50,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch works for a specific author by OpenAlex ID.
        
        Args:
            openalex_id: OpenAlex author ID (e.g., "https://openalex.org/A123456")
            per_page: Results per page
            max_pages: Maximum pages to fetch
            
        Returns:
            List of work items
        """
        # Extract ID from URL if needed
        author_id = openalex_id.replace("https://openalex.org/", "")
        
        all_works = []
        page = 1
        
        while page <= max_pages:
            url = (
                f"{self.base_url}/works"
                f"?filter=author.id:{author_id}"
                f"&per_page={per_page}"
                f"&page={page}"
            )
            
            try:
                data = await self._request_with_retry(url)
                results = data.get("results", [])
                
                if not results:
                    break
                
                all_works.extend(results)
                
                meta = data.get("meta", {})
                total_count = meta.get("count", 0)
                
                if len(all_works) >= total_count:
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"Error fetching works for {author_id}: {e}")
                break
        
        return all_works
