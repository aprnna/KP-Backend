"""
Scraper services package.
"""

from app.services.scraper.base import BaseScraper
from app.services.scraper.sinta_article import SintaArticleScraper
from app.services.scraper.sinta_author import SintaAuthorScraper
from app.services.scraper.utils import normalize_name, strip_titles

__all__ = [
    "BaseScraper",
    "SintaArticleScraper",
    "SintaAuthorScraper",
    "normalize_name",
    "strip_titles",
]
