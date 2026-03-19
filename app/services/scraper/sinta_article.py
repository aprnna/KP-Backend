"""
SINTA Article Scraper.

Scrapes articles from SINTA author profile pages.
Replaces the previous Crossref API scraper.

Logic adapted from:
  code_scraping_jurnal_unikom/jurnal/scraping_jurnal.ipynb

For each author (identified by id_sinta) it fetches 4 views:
  scopus | garuda | googlescholar | rama
and extracts article metadata from the HTML list items.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from bs4 import BeautifulSoup

from app.services.scraper.base import BaseScraper
from app.core.config import settings


logger = logging.getLogger(__name__)

# Maximum in-flight per-author scraping tasks.
MAX_CONCURRENT_AUTHORS = 3

SINTA_VIEWS = ["scopus", "garuda", "googlescholar", "rama"]


class SintaArticleScraper(BaseScraper):
    """
    Scraper for SINTA author article lists.

    Hits four SINTA profile view pages per author and parses the HTML
    `.ar-list-item` elements to extract article metadata.
    Results are mapped to the `sinta_articles` table columns.
    """

    def __init__(self, request_delay: float = None, max_retries: int = None):
        super().__init__(
            base_url=settings.sinta_base_url,
            request_delay=request_delay or settings.sinta_request_delay,
            max_retries=max_retries or settings.sinta_max_retries,
        )

    async def _fetch_html(self, url: str) -> str:
        """
        Fetch raw HTML at *url* using the base scraper's retry + rate-limit
        logic. The base client sends JSON Accept by default; SINTA returns HTML
        regardless, so we read `.text` directly from the raw response.

        Returns the response text, or an empty string on failure.
        """
        if not self._client:
            raise RuntimeError("HTTP client not initialised. Use 'async with'.")

        await self._rate_limit()
        for attempt in range(self.max_retries):
            try:
                response = await self._client.get(url)
                if response.status_code == 200:
                    return response.text
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "sinta_rate_limited",
                        extra={"url": url, "retry_after_sec": retry_after},
                    )
                    await asyncio.sleep(retry_after)
                    continue
                logger.warning(
                    "sinta_bad_status",
                    extra={"url": url, "status": response.status_code, "attempt": attempt + 1},
                )
                await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning(
                    "sinta_fetch_error",
                    extra={"url": url, "error": str(exc), "attempt": attempt + 1},
                )
                await asyncio.sleep(2 ** attempt)
        return ""

    @staticmethod
    def _extract_profile_author_name(soup: BeautifulSoup) -> Optional[str]:
        """Best-effort extraction of profile owner's name from page header."""
        selectors = [
            ".au-name",
            ".author-name",
            ".profile-name",
            ".caption h3",
            "h3",
        ]
        for selector in selectors:
            tag = soup.select_one(selector)
            if not tag:
                continue
            name = tag.get_text(" ", strip=True)
            if name and len(name) <= 120:
                return name
        return None

    @staticmethod
    def _normalize_cited(value: Optional[str]) -> Optional[str]:
        """Extract numeric cited count (e.g. '2 cited' -> '2')."""
        if not value:
            return None
        match = re.search(r"\d+", value)
        return match.group(0) if match else None

    @staticmethod
    def _normalize_doi(value: Optional[str]) -> Optional[str]:
        """Extract DOI and trim common prefixes from mixed text."""
        if not value:
            return None

        text = value.strip()

        # Remove common DOI labels and URL prefixes.
        text = re.sub(r"(?i)^doi\s*[:\-]?\s*", "", text)
        text = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", text)

        # Extract canonical DOI pattern if present.
        match = re.search(r"10\.\d{4,9}/\S+", text)
        if match:
            return match.group(0).rstrip(".,;)")

        return text or None

    @staticmethod
    def _normalize_sinta_rank(value: Optional[str]) -> Optional[int]:
        """Extract numeric SINTA rank (e.g. 'Accred : Sinta 4' -> 4)."""
        if not value:
            return None

        match = re.search(r"(?i)sinta\s*(\d+)", value)
        if match:
            return int(match.group(1))

        # Fallback: any number in accreditation text.
        fallback = re.search(r"\d+", value)
        if fallback:
            try:
                return int(fallback.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_authors(value: Optional[str], owner_name: Optional[str]) -> Optional[str]:
        """Normalize author list into semicolon-separated format."""
        if not value:
            return None

        text = value.strip()

        # Pattern: "Author Order : X of N" -> put owner name at position X.
        if re.search(r"(?i)author\s*order", text):
            order_match = re.search(r"(?i)author\s*order\s*:?\s*(\d+)", text)
            total_match = re.search(r"(?i)of\s*(\d+)", text)
            author_order = int(order_match.group(1)) if order_match else 1
            total_authors = int(total_match.group(1)) if total_match else 1
            author_order = max(author_order, 1)
            total_authors = max(total_authors, 1)
            author_order = min(author_order, total_authors)

            display_name = (owner_name or "unknown").strip() or "unknown"
            author_list = ["unknown"] * total_authors
            author_list[author_order - 1] = display_name
            return "; ".join(author_list)

        # Convert comma-separated names to semicolon-separated names.
        names = [part.strip() for part in text.split(",") if part.strip()]
        if names:
            return "; ".join(names)

        return text or None

    def _parse_article_items(
        self, html: str, id_sinta: int, view: str
    ) -> List[Dict[str, Any]]:
        """
        Parse HTML of a SINTA profile view page.
        Returns a list of article dicts ready for DB insertion.
        """
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".ar-list-item")
        results: List[Dict[str, Any]] = []

        profile_author_name = self._extract_profile_author_name(soup)

        for item in items:
            # Title + link
            title_tag = item.select_one(".ar-title a")
            title = title_tag.get_text(strip=True) if title_tag else None
            link = title_tag.get("href") if title_tag else None

            # Year
            year_tag = item.select_one(".ar-year")
            year = year_tag.get_text(strip=True) if year_tag else None

            # Cited count
            cited_tag = item.select_one(".ar-cited")
            cited_raw = cited_tag.get_text(strip=True) if cited_tag else None
            cited = self._normalize_cited(cited_raw)

            # Quartile / accreditation
            quartile_tag = item.select_one(".ar-quartile")
            quartile = quartile_tag.get_text(strip=True) if quartile_tag else None

            # Journal / publisher
            pub_tag = item.select_one(".ar-pub")
            publisher = pub_tag.get_text(strip=True) if pub_tag else None

            # Authors string — look for anchor texts containing "Authors" or "Author Order"
            authors_str: Optional[str] = None
            for anchor in item.find_all("a"):
                text = anchor.get_text(strip=True)
                if "Authors :" in text:
                    authors_str = text.replace("Authors :", "").strip()
                elif "Author Order" in text:
                    authors_str = text.strip()
            authors_str = self._normalize_authors(authors_str, profile_author_name)

            row = {
                "id_sinta": id_sinta,
                "source": view,
                "article_title": title,
                "authors": authors_str,
                "publisher": publisher,
                "year": year,
                "cited": cited,
                "doi": None,
                "quartile": quartile,
                "sinta_rank": None,
                "url": link,
                "scraped_at": datetime.utcnow(),
            }

            if view == "garuda":
                row["cited"] = None
                row["doi"] = self._normalize_doi(cited_raw)
                row["quartile"] = None
                row["sinta_rank"] = self._normalize_sinta_rank(quartile)

            results.append(row)
        return results

    async def scrape_author(
        self,
        id_sinta: int,
        job_id: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Scrape all articles for one author across all 4 SINTA views.

        Args:
            id_sinta: SINTA author ID
            job_id:   Job identifier for structured logging

        Returns:
            List of article dicts mapped to sinta_articles columns.
        """
        all_articles: List[Dict[str, Any]] = []
        t0 = time.monotonic()

        for view in SINTA_VIEWS:
            url = f"{self.base_url}/authors/profile/{id_sinta}/?view={view}"
            try:
                html = await self._fetch_html(url)
                if not html:
                    logger.warning(
                        "sinta_article_empty_response",
                        extra={"job_id": job_id, "id_sinta": id_sinta, "view": view},
                    )
                    continue
                articles = self._parse_article_items(html, id_sinta, view)
                all_articles.extend(articles)
                logger.debug(
                    "sinta_article_view_done",
                    extra={
                        "job_id": job_id,
                        "id_sinta": id_sinta,
                        "view": view,
                        "count": len(articles),
                    },
                )
            except Exception as exc:
                logger.error(
                    "sinta_article_view_error",
                    extra={"job_id": job_id, "id_sinta": id_sinta, "view": view, "error": str(exc)},
                )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "sinta_article_author_done",
            extra={
                "job_id": job_id,
                "id_sinta": id_sinta,
                "total_articles": len(all_articles),
                "duration_ms": elapsed_ms,
            },
        )
        return all_articles

    async def scrape(
        self,
        sinta_ids: List[int],
        job_id: str = None,
        on_progress: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method — fetch articles for multiple SINTA author IDs.

        Uses asyncio.Semaphore(MAX_CONCURRENT_AUTHORS) to limit parallelism
        without overloading the SINTA server.

        Args:
            sinta_ids:   List of SINTA author IDs to scrape.
            job_id:      Job identifier for logging.
            on_progress: Optional callback(id_sinta, processed, total).

        Returns:
            Flat list of article dicts for all authors.
        """
        total = len(sinta_ids)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AUTHORS)

        async def _scrape_one(idx: int, id_sinta: int) -> List[Dict[str, Any]]:
            async with semaphore:
                result = await self.scrape_author(id_sinta, job_id=job_id)
            if on_progress:
                on_progress(id_sinta, idx + 1, total)
            return result

        tasks = [_scrape_one(i, sid) for i, sid in enumerate(sinta_ids)]
        nested = await asyncio.gather(*tasks)
        all_results = [item for sublist in nested for item in sublist]

        logger.info(
            "sinta_article_scrape_complete",
            extra={"job_id": job_id, "total_authors": total, "total_articles": len(all_results)},
        )
        return all_results
