import logging
import urllib.parse
from typing import Any, Dict, List
from datetime import datetime

from app.services.scraper.base import BaseScraper


logger = logging.getLogger(__name__)


class CrossrefScraper(BaseScraper):
    """
    Scraper for Crossref API to enrich Sinta article data.
    """

    def __init__(self):
        super().__init__(
            base_url="https://api.crossref.org",
            request_delay=0.2,  # Be polite to Crossref API
            max_retries=3,
            timeout=30.0,
        )

    async def scrape(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Not used directly. We use enrich_articles instead.
        """
        return []

    async def enrich_articles(self, articles: List[Dict[str, Any]]) -> None:
        """
        Enrich a list of Sinta article dictionaries with Crossref data.
        Prioritizes DOI lookup, falls back to title search with verification.
        Modifies the dictionaries in-place.
        """
        for article in articles:
            doi = article.get("doi")
            title = article.get("article_title")
            
            if not doi and not title:
                continue

            try:
                item = None
                
                # 1. Try DOI lookup first if available
                if doi:
                    # Straight lookup: /works/{doi}
                    url = f"{self.base_url}/works/{urllib.parse.quote(doi)}"
                    data = await self._request_with_retry(url)
                    if data and data.get("status") == "ok" and "message" in data:
                        # For direct DOI lookup, message IS the item
                        item = data["message"]
                
                # 2. Fallback to title search if no DOI or DOI-lookup didn't yield an item
                if not item and title:
                    params = {
                        "rows": 1,
                        "query.title": title # Crossref-specific query param
                    }
                    data = await self._request_with_retry(f"{self.base_url}/works", params=params)
                    if data and "message" in data and "items" in data["message"]:
                        items = data["message"]["items"]
                        if items:
                            potential_item = items[0]
                            # CRITICAL: Verify title match for search-based results
                            if self._is_title_match(title, potential_item):
                                item = potential_item

                # 3. Apply enrichment if we found a verified match
                if item:
                    extracted_data = self._extract_crossref_data(item)
                    
                    # Update article with extracted non-empty attributes
                    for key, val in extracted_data.items():
                        if val is not None:
                            article[key] = val

                    # Always add crossref to source if we successfully enriched
                    current_source = article.get("source", "")
                    if current_source:
                        if "crossref" not in current_source.lower():
                            # source is now String(255), so concat is safe
                            article["source"] = f"{current_source},crossref"
                    else:
                        article["source"] = "crossref"

            except Exception as e:
                logger.warning(
                    "crossref_enrich_error",
                    extra={"title": title, "doi": doi, "error": str(e)}
                )

    def _is_title_match(self, original_title: str, item: Dict[str, Any]) -> bool:
        """
        Check if the title from Crossref matches our original title.
        Uses alphanumeric normalization for comparison.
        """
        crossref_titles = item.get("title", [])
        if not crossref_titles:
            return False
            
        crossref_title = crossref_titles[0]
        
        def normalize(t: str) -> str:
            if not t: return ""
            return "".join(c for c in t.lower() if c.isalnum())

        return normalize(original_title) == normalize(crossref_title)

    def _extract_crossref_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and map fields from a single Crossref JSON item 
        to our internal article schema. 
        """
        data: Dict[str, Any] = {}

        # pdf_link -> resource.primary.URL
        resource = item.get("resource", {})
        primary = resource.get("primary", {})
        if primary.get("URL"):
            data["pdf_link"] = primary["URL"]

        # raw_type -> type
        if item.get("type"):
            data["raw_type"] = item["type"]

        # issn -> issn-type.value, issn_type -> issn-type.type
        issn_types = item.get("issn-type", [])
        if issn_types:
            data["issn"] = issn_types[0].get("value")
            data["issn_type"] = issn_types[0].get("type")

        # indexed_date_time -> indexed.date-time
        indexed = item.get("indexed", {})
        if indexed.get("date-time"):
            dt_str = indexed.get("date-time")
            try:
                # Replace 'Z' with '+00:00' for isoformat if needed
                dt_parsed = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                data["indexed_date_time"] = dt_parsed
            except ValueError:
                pass

        # indexed_date_parts -> indexed.date-parts
        date_parts = indexed.get("date-parts", [])
        if date_parts and date_parts[0]:
            parts = date_parts[0]
            data["indexed_date_parts"] = "-".join(str(p) for p in parts)

        # short_journal_title -> short-container-title
        short_titles = item.get("short-container-title", [])
        if short_titles:
            data["short_journal_title"] = short_titles[0]

        # journal_title -> container-title
        titles = item.get("container-title", [])
        if titles:
            data["journal_title"] = titles[0]

        # issue -> issue
        if item.get("issue"):
            data["issue"] = item["issue"]

        # volume -> volume
        if item.get("volume"):
            data["volume"] = item["volume"]

        return data
