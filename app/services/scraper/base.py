"""
Base scraper with common functionality.
Provides retry logic, rate limiting, and error handling.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
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
    """Raised for unrecoverable API errors (4xx client errors)."""
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
    - Correct 429 rate-limit handling (waits without consuming retry budget)
    - Retry on 5xx transient errors; immediate raise on 4xx client errors
    - Rate limiting between requests
    - Structured logging with context fields
    """

    def __init__(
        self,
        base_url: str,
        request_delay: float = 0.5,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.base_url = base_url
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0

    async def __aenter__(self):
        """Async context manager entry — initializes the HTTP client."""
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
        """Async context manager exit — closes the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self):
        """
        Enforce minimum delay between consecutive requests.
        Uses event loop time for accurate measurement.
        """
        loop = asyncio.get_event_loop()
        now = loop.time()
        elapsed = now - self._last_request_time
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        self._last_request_time = loop.time()

    async def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        """
        Make HTTP request with:
        - Retry + exponential backoff on timeout / network errors / 5xx errors.
        - 429 handling: sleep Retry-After (default 5s) then retry WITHOUT
          decrementing the retry counter, so rate-limit waits don't waste budget.
        - Immediate raise on 4xx client errors (nothing to retry).

        Returns:
            Parsed JSON response

        Raises:
            ApiError: On 4xx or when all retries are exhausted
            ScraperError: If client is not initialized
        """
        if not self._client:
            raise ScraperError("HTTP client not initialized. Use 'async with' context manager.")

        last_error = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()

                start_time = time.monotonic()

                if method.upper() == "GET":
                    response = await self._client.get(url, params=params)
                else:
                    response = await self._client.request(method, url, params=params)

                elapsed_ms = int((time.monotonic() - start_time) * 1000)

                # --- 429 Rate Limit: wait without consuming retry budget ---
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "api_rate_limited",
                        extra={
                            "url": url,
                            "retry_after_sec": retry_after,
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(retry_after)
                    continue  # Does NOT increment the attempt counter

                # --- 5xx Server Errors: transient, worth retrying ---
                if response.status_code >= 500:
                    wait_time = (2 ** attempt) * 1
                    logger.warning(
                        "api_server_error_retry",
                        extra={
                            "url": url,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "wait_sec": wait_time,
                        },
                    )
                    last_error = ApiError(
                        f"Server error {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text[:500],
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # --- 4xx Client Errors: caller issue, raise immediately ---
                if response.status_code >= 400:
                    raise ApiError(
                        f"Client error: {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text[:500],
                    )

                data = response.json()

                logger.debug(
                    "api_request_ok",
                    extra={"url": url, "status": response.status_code, "elapsed_ms": elapsed_ms},
                )

                return data

            except httpx.TimeoutException as e:
                last_error = e
                wait_time = (2 ** attempt) * 1
                logger.warning(
                    "api_timeout_retry",
                    extra={"url": url, "attempt": attempt + 1, "wait_sec": wait_time},
                )
                await asyncio.sleep(wait_time)

            except httpx.RequestError as e:
                last_error = e
                wait_time = (2 ** attempt) * 1
                logger.warning(
                    "api_request_error_retry",
                    extra={"url": url, "error": str(e), "attempt": attempt + 1, "wait_sec": wait_time},
                )
                await asyncio.sleep(wait_time)

            except ApiError:
                raise  # 4xx errors propagate immediately

            except Exception as e:
                last_error = e
                logger.error(
                    "api_unexpected_error",
                    extra={"url": url, "error": str(e), "attempt": attempt + 1},
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise

        raise ApiError(f"All {self.max_retries} retry attempts exhausted: {last_error}")

    @abstractmethod
    async def scrape(self, **kwargs) -> List[Dict[str, Any]]:
        """Main scraping method to be implemented by subclasses."""
        pass

    def get_stats(self) -> Dict[str, Any]:
        """Return scraper configuration stats."""
        return {
            "base_url": self.base_url,
            "request_delay": self.request_delay,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
        }
