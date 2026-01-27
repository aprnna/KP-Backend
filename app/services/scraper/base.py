"""
Base scraper with common functionality.
Provides retry logic, rate limiting, and error handling.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base exception for scraper errors"""
    pass


class RateLimitError(ScraperError):
    """Raised when rate limit is hit"""
    pass


class ApiError(ScraperError):
    """Raised for API errors"""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BaseScraper(ABC):
    """
    Base class for all scrapers.
    Provides common functionality:
    - Async HTTP client with timeout
    - Retry with exponential backoff
    - Rate limiting
    - Error handling and logging
    """

    def __init__(
        self,
        base_url: str,
        request_delay: float = 0.5,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        """
        Initialize the base scraper.
        
        Args:
            base_url: Base URL for the API
            request_delay: Delay between requests in seconds
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0

    async def __aenter__(self):
        """Async context manager entry"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            headers={
                "User-Agent": f"AcademicScraper/1.0 ({settings.app_name})",
                "Accept": "application/json",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """
        Enforce rate limiting between requests.
        Ensures minimum delay between consecutive requests.
        """
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry and exponential backoff.
        
        Args:
            url: Request URL
            params: Query parameters
            method: HTTP method
            
        Returns:
            Parsed JSON response
            
        Raises:
            ApiError: If all retries fail
        """
        if not self._client:
            raise ScraperError("Client not initialized. Use async context manager.")
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                start_time = datetime.utcnow()
                
                if method.upper() == "GET":
                    response = await self._client.get(url, params=params)
                else:
                    response = await self._client.request(method, url, params=params)
                
                elapsed_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s before retry")
                    await asyncio.sleep(retry_after)
                    continue
                
                # Handle other errors
                if response.status_code >= 400:
                    raise ApiError(
                        f"API error: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text[:500]
                    )
                
                # Parse JSON response
                data = response.json()
                
                logger.debug(f"Request to {url} completed in {elapsed_ms}ms")
                
                return data
                
            except httpx.TimeoutException as e:
                last_error = e
                wait_time = (2 ** attempt) * 1  # Exponential backoff
                logger.warning(f"Timeout on attempt {attempt + 1}, retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
                
            except httpx.RequestError as e:
                last_error = e
                wait_time = (2 ** attempt) * 1
                logger.warning(f"Request error on attempt {attempt + 1}: {e}, retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
                
            except ApiError:
                raise
                
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        
        raise ApiError(f"All {self.max_retries} retry attempts failed: {last_error}")

    @abstractmethod
    async def scrape(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Main scraping method to be implemented by subclasses.
        
        Returns:
            List of scraped data items
        """
        pass

    def get_stats(self) -> Dict[str, Any]:
        """
        Get scraper statistics.
        
        Returns:
            Dictionary with scraper stats
        """
        return {
            "base_url": self.base_url,
            "request_delay": self.request_delay,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
        }
