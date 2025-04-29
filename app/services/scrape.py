import asyncio


from app.db import MongoClient
from app.models.news_collection import NewsCollection

from .page_parser import GoogleNewsParser, PageParser
from .scraper import Scraper


async def add_entries_to_db(client: MongoClient, entries: NewsCollection):
    await client.add_news_entries(entries)


async def scrape_pages(client: MongoClient, parser: PageParser):
    for url in parser.urls:
        soup = await Scraper.get_soup(url)
        entries = await Scraper.get_news(soup, parser, 10)

        if entries:
            await add_entries_to_db(client, entries)


async def main():
    parsers: list[PageParser] = [GoogleNewsParser()]
    client = MongoClient()

    for parser in parsers:
        await scrape_pages(client, parser)


if __name__ == "__main__":
    asyncio.run(main())
