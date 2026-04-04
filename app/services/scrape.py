import asyncio
import sys


from app.db import MongoClient
from app.models.news_collection import NewsCollection

from .logger import get_logger
from .page_parser import GoogleNewsParser, PageParser
from .scraper import Scraper

logger = get_logger(__name__)


async def add_entries_to_db(client: MongoClient, entries: NewsCollection):
    await client.add_news_entries(entries)
    logger.info(f"Added {len(entries.entries)} entries to database")


async def scrape_pages(client: MongoClient, parser: PageParser):
    logger.info(f"Starting scrape with {parser.__class__.__name__}")
    for url in parser.urls:
        soup = await Scraper.get_soup(url)
        entries = await Scraper.get_news(soup, parser, 10)

        if entries:
            await add_entries_to_db(client, entries)
    logger.info(f"Completed scrape with {parser.__class__.__name__}")


async def main():
    logger.info("Starting scrape job")
    parsers: list[PageParser] = [GoogleNewsParser()]
    client = MongoClient()

    for parser in parsers:
        await scrape_pages(client, parser)
    logger.info("Scrape job completed")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
