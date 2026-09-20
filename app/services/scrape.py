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
    GoogleNewsRSSParser,
    LoopNewsParser,
    NationNewsParser,
    PageParser,
)
from .scraper import Scraper

logger = get_logger(__name__)

ENTRIES_PER_URL = 10
"""How many entries to keep from each fetched page, unless the parser sets
``entries_per_url``."""

PRIMARY_PARSERS: list[type[PageParser]] = [
    NationNewsParser,
    BarbadosTodayParser,
    BBCBarbadosParser,
]
"""The outlets' own feeds. run() finishes these before starting any aggregator so
their copies (with snippets and publisher links) are the ones stored; the
aggregator's overlapping items are then the duplicates the unique index rejects,
and add_news_entries() backfills any earlier snippet-less copy from them."""

AGGREGATOR_PARSERS: list[type[PageParser]] = [GoogleNewsRSSParser]
"""Feeds that re-surface other outlets' articles; run after PRIMARY_PARSERS."""

PARSERS: list[type[PageParser]] = [*PRIMARY_PARSERS, *AGGREGATOR_PARSERS]
"""Sources fetched on every run. Register a new parser in one of the two lists above."""

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
        amount: The maximum number of entries to keep, unless the parser declares its own
            ``entries_per_url``, which wins.

    Returns:
        The number of entries parsed. Any failure is logged and counts as zero so the
        caller can carry on with the other sources.
    """
    source = parser.source_name
    limit = parser.entries_per_url or amount
    try:
        text = await scraper.fetch_text(url, timeout=parser.request_timeout)
        collection = Scraper.get_news(text, parser, limit)
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
    """Scrape every URL of every parser over one shared session, in two phases.

    The outlets' own feeds are fetched concurrently and stored first; only then
    are the aggregators fetched, so an outlet being slow can never let the
    aggregator's copy of its article win the race into the database.

    Args:
        parsers: The parsers to run; defaults to :data:`PARSERS`.
        amount: The maximum number of entries to keep per URL, for parsers that do not
            set ``entries_per_url`` themselves.

    Returns:
        The total number of entries parsed across all sources.
    """
    active = list(PARSERS if parsers is None else parsers)
    phases = [
        [parser for parser in active if parser not in AGGREGATOR_PARSERS],
        [parser for parser in active if parser in AGGREGATOR_PARSERS],
    ]
    url_count = sum(len(parser.urls) for parser in active)
    logger.info("Starting scrape job: sources=%d urls=%d", len(active), url_count)

    total = 0
    async with Scraper() as scraper:
        for phase in (phase for phase in phases if phase):
            targets = [(parser, url) for parser in phase for url in parser.urls]
            results = await asyncio.gather(
                *(
                    scrape_source(scraper, parser, url, amount)
                    for parser, url in targets
                ),
                return_exceptions=True,
            )
            for (parser, url), result in zip(targets, results, strict=True):
                if isinstance(result, BaseException):
                    logger.error(
                        "source=%s url=%s failed: %r", parser.source_name, url, result
                    )
                else:
                    total += result

    logger.info("Scrape job completed: urls=%d parsed=%d", url_count, total)
    return total


async def main() -> None:
    """Entry point for the twice-daily job."""
    # The web tier creates this index at boot, but the scraper is its own
    # process and relies on it for cross-run deduplication.
    try:
        await client.ensure_indexes()
    except Exception:
        logger.exception("Failed to ensure database indexes; continuing without them")

    await run()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
