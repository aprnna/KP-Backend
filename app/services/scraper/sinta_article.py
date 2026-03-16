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
            cited = cited_tag.get_text(strip=True) if cited_tag else None

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

            results.append({
                "id_sinta": id_sinta,
                "source": view,
                "article_title": title,
                "authors": authors_str,
                "publisher": publisher,
                "year": year,
                "cited": cited,
                "quartile": quartile,
                "url": link,
                "scraped_at": datetime.utcnow(),
            })

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
