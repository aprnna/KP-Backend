import logging
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import quote

from app.services.scraper.base import BaseScraper
from app.services.scraper.utils import strip_titles
from app.core.config import settings

logger = logging.getLogger(__name__)

class SintaScrapper(BaseScraper):
        def __init__(
            self,
            rows_per_request: int = None,
            max_offset: int = None,
            request_delay: float = None,
            max_retries: int = None,
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