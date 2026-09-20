"""HTTP fetching for the scrape job.

A :class:`Scraper` owns one ``aiohttp.ClientSession`` for a whole run, sends browser-like
headers, enforces a total timeout per request and retries transient failures with
exponential backoff.
"""

import logging
from types import TracebackType
from typing import Any, Self

import aiohttp
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.models.news_collection import NewsCollection

from .logger import get_logger
from .page_parser import PageParser

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
        "text/html;q=0.8, */*;q=0.7"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
RETRYABLE_ERRORS = (aiohttp.ClientError, TimeoutError)


class Scraper:
    """Fetches pages over a single shared HTTP session.

    Use as an async context manager so the session is closed at the end of the run::

        async with Scraper() as scraper:
            text = await scraper.fetch_text(url)

    Args:
        session: An existing session to reuse; when omitted the scraper creates (and owns)
            one with the default headers and timeout on entry.
    """

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """The live session; raises if the scraper has not been entered."""
        if self._session is None:
            raise RuntimeError(
                "Scraper must be used as 'async with Scraper() as scraper'"
            )
        return self._session

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_text(self, url: str, timeout: float | None = None) -> str:
        """GET ``url`` and return the decoded body, retrying transient failures.

        Args:
            url: The page or feed to fetch.
            timeout: Total seconds to allow for this request; ``None`` keeps the session
                default of :data:`REQUEST_TIMEOUT`.

        Returns:
            The response body as text.

        Raises:
            aiohttp.ClientError: On a network error or non-2xx status after three attempts.
            TimeoutError: When the request exceeds the total timeout after three attempts.
        """
        request_options: dict[str, Any] = {}
        if timeout is not None:
            request_options["timeout"] = aiohttp.ClientTimeout(total=timeout)
        logger.info("Fetching %s", url)
        async with self.session.get(url, **request_options) as response:
            response.raise_for_status()
            text = await response.text()
        logger.info(
            "Fetched %s: HTTP %d, %d characters", url, response.status, len(text)
        )
        return text

    @staticmethod
    def get_news(
        text: str, parser: type[PageParser], amount: int
    ) -> NewsCollection | None:
        """Parse fetched text with ``parser`` and log how many entries came out.

        Args:
            text: The raw response body.
            parser: The source's parser class.
            amount: The maximum number of entries to return.

        Returns:
            The parsed collection, or ``None`` when nothing usable was found.
        """
        collection = parser.parse_entries(text, amount)
        count = len(collection.entries) if collection is not None else 0
        logger.info("%s parsed %d entries", parser.__name__, count)
        return collection
