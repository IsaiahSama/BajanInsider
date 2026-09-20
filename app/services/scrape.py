"""Scrape job: fetch every registered source, parse it and store the entries.

Run with ``python -m app.services.scrape``. Every source URL is fetched, parsed and stored
independently, so one site being down never aborts the run.
"""

import asyncio
import sys
from collections.abc import Sequence

from app.db.mongo_client import client

from .logger import get_logger
from .page_parser import (
    BarbadosAdvocateParser,
    BarbadosTodayParser,
    BBCBarbadosParser,
    LoopNewsParser,
    NationNewsParser,
    PageParser,
)
from .scraper import Scraper

logger = get_logger(__name__)

ENTRIES_PER_URL = 10
"""How many entries to keep from each fetched page."""

PARSERS: list[type[PageParser]] = [NationNewsParser, BarbadosTodayParser, BBCBarbadosParser]
"""Sources fetched on every run. Register a new parser here."""

DORMANT_PARSERS: list[type[PageParser]] = [LoopNewsParser, BarbadosAdvocateParser]
"""Implemented sources that are not fetched because the outlet is offline (see each class
docstring). Move one back into :data:`PARSERS` if it returns."""


async def scrape_source(
    scraper: Scraper, parser: type[PageParser], url: str, amount: int = ENTRIES_PER_URL
) -> int:
    """Fetch, parse and store one source URL.

    Args:
        scraper: The entered scraper whose session is used for the request.
        parser: The source's parser class.
        url: The page or feed to fetch.
        amount: The maximum number of entries to keep.

    Returns:
        The number of entries parsed. Any failure is logged and counts as zero so the
        caller can carry on with the other sources.
    """
    source = parser.source_name
    try:
        text = await scraper.fetch_text(url, timeout=parser.request_timeout)
        collection = Scraper.get_news(text, parser, amount)
        if collection is None:
            logger.warning("source=%s url=%s parsed=0", source, url)
            return 0
        await client.add_news_entries(collection)
    except Exception:
        logger.exception("source=%s url=%s failed", source, url)
        return 0
    parsed = len(collection.entries)
    logger.info("source=%s url=%s parsed=%d", source, url, parsed)
    return parsed


async def run(
    parsers: Sequence[type[PageParser]] | None = None, amount: int = ENTRIES_PER_URL
) -> int:
    """Scrape every URL of every parser concurrently over one shared session.

    Args:
        parsers: The parsers to run; defaults to :data:`PARSERS`.
        amount: The maximum number of entries to keep per URL.

    Returns:
        The total number of entries parsed across all sources.
    """
    active = list(PARSERS if parsers is None else parsers)
    targets = [(parser, url) for parser in active for url in parser.urls]
    logger.info("Starting scrape job: sources=%d urls=%d", len(active), len(targets))

    async with Scraper() as scraper:
        results = await asyncio.gather(
            *(scrape_source(scraper, parser, url, amount) for parser, url in targets),
            return_exceptions=True,
        )

    total = 0
    for (parser, url), result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("source=%s url=%s failed: %r", parser.source_name, url, result)
        else:
            total += result
    logger.info("Scrape job completed: urls=%d parsed=%d", len(targets), total)
    return total


async def main() -> None:
    """Entry point for the twice-daily job."""
    await run()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
