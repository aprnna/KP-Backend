"""
SINTA Author Scraper.

Scrapes author profile data and bibliometric stats from SINTA.
Replaces the previous OpenAlex API scraper.

Logic adapted from:
  code_scraping_jurnal_unikom/author/scrapting.ipynb

Two-phase scraping per run:
  1. Affiliation list page (paged) — id_sinta, fullname, major, scores
  2. Per-author detail profile page — metrics table (Scopus + GScholar)
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

# Column mapping: HTML table label → sinta_authors column, per source
METRICS_MAPPING_SCOPUS: Dict[str, str] = {
    "Article": "s_article_scopus",
    "Citation": "s_citation_scopus",
    "Cited Document": "s_cited_document_scopus",
    "h-index": "s_hindex_scopus",
    "i10-Index": "s_i10_index_scopus",
    "G-Index": "s_gindex_scopus",
}

METRICS_MAPPING_GSCHOLAR: Dict[str, str] = {
    "Article": "s_article_gscholar",
    "Citation": "s_citation_gscholar",
    "Cited Document": "s_cited_document_gscholar",
    "h-index": "s_hindex_gscholar",
    "i10-Index": "s_i10_index_gscholar",
    "G-Index": "s_gindex_gscholar",
}


def _to_int(value: str) -> Optional[int]:
    """Convert a scraped string to int, returning None on failure."""
    try:
        return int(value.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


class SintaAuthorScraper(BaseScraper):
    """
    Scraper for SINTA author profiles.

    Phase 1: Fetches the Unikom affiliation author list (paginated).
    Phase 2: Fetches individual profile pages to collect detailed metrics.
    Results are mapped to the `sinta_authors` table columns.
    """

    def __init__(self, request_delay: float = None, max_retries: int = None):
        super().__init__(
            base_url=settings.sinta_base_url,
            request_delay=request_delay or settings.sinta_request_delay,
            max_retries=max_retries or settings.sinta_max_retries,
        )
        self._affiliation_id = settings.sinta_affiliation_id

    # ------------------------------------------------------------------
    # Low-level HTML fetch (SINTA returns HTML, not JSON)
    # ------------------------------------------------------------------

    async def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML with retry + rate limiting."""
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
                    await asyncio.sleep(retry_after)
                    continue
                await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning(
                    "sinta_author_fetch_error",
                    extra={"url": url, "error": str(exc), "attempt": attempt + 1},
                )
                await asyncio.sleep(2 ** attempt)
        return ""

    # ------------------------------------------------------------------
    # Phase 1 — Affiliation list
    # ------------------------------------------------------------------

    def _parse_affiliation_page(self, html: str) -> List[Dict[str, Any]]:
        """
        Parse one page of the SINTA affiliation author list.
        Returns a list of partial author dicts (no metrics yet).
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.col-lg")
        results: List[Dict[str, Any]] = []

        for card in cards:
            name_div = card.find("div", class_="profile-name")
            if not name_div:
                continue

            name_tag = name_div.find("a")
            fullname = name_tag.get_text(strip=True) if name_tag else name_div.get_text(strip=True)
            profile_url = name_tag.get("href") if name_tag else None

            dept_div = card.find("div", class_="profile-dept")
            major = dept_div.get_text(strip=True) if dept_div else None

            id_div = card.find("div", class_="profile-id")
            raw_id = id_div.get_text(strip=True).replace("ID :", "").strip() if id_div else None
            id_sinta = _to_int(raw_id)

            # Sinta scores from stat blocks
            sinta_score = sinta_score_3yr = affil_score = affil_score_3yr = None
            for col in card.select("div.col"):
                label_el = col.find("div", class_="stat-text")
                value_el = col.find("div", class_="stat-num")
                if not label_el or not value_el:
                    continue
                label = label_el.get_text(strip=True)
                value = value_el.get_text(strip=True)
                if label == "SINTA Score":
                    sinta_score = _to_int(value)
                elif label == "SINTA Score 3Yr":
                    sinta_score_3yr = _to_int(value)
                elif label == "Affil Score":
                    affil_score = _to_int(value)
                elif label == "Affil Score 3Yr":
                    affil_score_3yr = _to_int(value)

            results.append({
                "id_sinta": id_sinta,
                "fullname": fullname,
                "major": major,
                "profile_url": profile_url,
                "sinta_score_overall": sinta_score,
                "sinta_score_3yr": sinta_score_3yr,
                "affil_score": affil_score,
                "affil_score_3yr": affil_score_3yr,
            })

        return results

    async def scrape_affiliation_list(self, job_id: str = None) -> List[Dict[str, Any]]:
        """
        Collect the full list of authors from the SINTA affiliation page.
        Paginates until an empty page is returned.
        """
        all_authors: List[Dict[str, Any]] = []
        page = 1

        while True:
            url = f"{self.base_url}/affiliations/authors/{self._affiliation_id}/?page={page}"
            html = await self._fetch_html(url)
            if not html:
                break

            page_authors = self._parse_affiliation_page(html)
            if not page_authors:
                break

            all_authors.extend(page_authors)
            logger.debug(
                "sinta_affiliation_page_done",
                extra={"job_id": job_id, "page": page, "count": len(page_authors)},
            )
            page += 1

        logger.info(
            "sinta_affiliation_list_done",
            extra={"job_id": job_id, "total_authors": len(all_authors)},
        )
        return all_authors

    # ------------------------------------------------------------------
    # Phase 2 — Detail profile
    # ------------------------------------------------------------------

    def _parse_profile_metrics(self, html: str) -> Dict[str, Any]:
        """
        Parse the detail profile page to extract:
        - subject_research (from ul.subject-list)
        - bibliometric metrics table (Scopus + GScholar columns)
        """
        soup = BeautifulSoup(html, "html.parser")
        metrics: Dict[str, Any] = {}

        # Subjects
        subject_section = soup.select_one("div.profile-subject ul.subject-list")
        if subject_section:
            subjects = [a.get_text(strip=True) for a in subject_section.select("li a")]
            metrics["subject_research"] = "; ".join(subjects) if subjects else None

        # Metrics table (3 columns: label | Scopus | GScholar)
        for row in soup.select("tbody tr"):
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            label = cols[0].get_text(strip=True)
            scopus_val = cols[1].get_text(strip=True)
            gscholar_val = cols[2].get_text(strip=True)

            if label in METRICS_MAPPING_SCOPUS:
                metrics[METRICS_MAPPING_SCOPUS[label]] = _to_int(scopus_val)
            if label in METRICS_MAPPING_GSCHOLAR:
                metrics[METRICS_MAPPING_GSCHOLAR[label]] = _to_int(gscholar_val)

        return metrics

    async def scrape_author_profile(
        self, id_sinta: int, job_id: str = None
    ) -> Dict[str, Any]:
        """
        Fetch and parse the detail profile page for one author.

        Returns a metrics dict ready to be merged into the author record.
        Returns an empty dict on failure so the caller can continue safely.
        """
        url = f"{self.base_url}/authors/profile/{id_sinta}"
        try:
            html = await self._fetch_html(url)
            if not html:
                return {}
            return self._parse_profile_metrics(html)
        except Exception as exc:
            logger.error(
                "sinta_author_profile_error",
                extra={"job_id": job_id, "id_sinta": id_sinta, "error": str(exc)},
            )
            return {}

    # ------------------------------------------------------------------
    # Main scrape method
    # ------------------------------------------------------------------

    async def scrape(
        self,
        sinta_ids: Optional[List[int]] = None,
        job_id: str = None,
        on_progress: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Full two-phase author scrape.

        Phase 1: Collect author list from SINTA affiliation page.
        Phase 2: Enrich each author with detail profile metrics.

        If *sinta_ids* is provided, Phase 1 is skipped and only those
        authors are enriched (used when authors already exist in the main DB).

        Returns:
            List of author dicts ready for upserting into `sinta_authors`.
        """
        t0 = time.monotonic()

        if sinta_ids is None:
            # Full run: discover from SINTA affiliation list
            partial_authors = await self.scrape_affiliation_list(job_id=job_id)
        else:
            # Incremental run: seed from provided IDs
            partial_authors = [{"id_sinta": sid} for sid in sinta_ids]

        total = len(partial_authors)
        results: List[Dict[str, Any]] = []

        for idx, author in enumerate(partial_authors):
            id_sinta = author.get("id_sinta")
            if not id_sinta:
                continue

            try:
                metrics = await self.scrape_author_profile(id_sinta, job_id=job_id)
                merged = {
                    **author,
                    **metrics,
                    "scraped_at": datetime.utcnow(),
                }
                results.append(merged)

                logger.debug(
                    "sinta_author_profile_done",
                    extra={"job_id": job_id, "id_sinta": id_sinta, "idx": idx + 1, "total": total},
                )

            except Exception as exc:
                logger.error(
                    "sinta_author_error",
                    extra={"job_id": job_id, "id_sinta": id_sinta, "error": str(exc)},
                )
                results.append({**author, "scraped_at": datetime.utcnow()})

            if on_progress:
                on_progress(id_sinta, idx + 1, total)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "sinta_author_scrape_complete",
            extra={"job_id": job_id, "total": total, "duration_ms": elapsed_ms},
        )
        return results
