"""
Scraper services package.
"""

from app.services.scraper.base import BaseScraper
from app.services.scraper.crossref import CrossrefScraper
from app.services.scraper.openalex import OpenAlexScraper
from app.services.scraper.utils import normalize_name, strip_titles

__all__ = [
    "BaseScraper",
    "CrossrefScraper",
    "OpenAlexScraper",
    "normalize_name",
    "strip_titles",
]
