"""This file handles the scraping logic for the news sources

This has been repurposed from the original"""

import aiohttp
from bs4 import BeautifulSoup

from app.models.news_collection import NewsCollection

from .logger import get_logger
from .page_parser import PageParser

logger = get_logger(__name__)

"""

Entry Format:

{
    "title": str,
    "content": str,
    "sourceName": str,
    "sourceLink": str,
    "dateScraped": str
}

"""


class Scraper:
    @staticmethod
    async def get_soup(url: str) -> BeautifulSoup:
        """Retrieves the beautiful Soup from the webpage

        Args:
            url (str): The url of the page to get and turn into Soup

        Returns:
            BeautifulSoup: The soup object"""

        logger.info(f"Fetching URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                html = await response.text()
                logger.info(f"Successfully fetched: {url}")
                return BeautifulSoup(html, "html.parser")

    @staticmethod
    async def get_news(
        soup: BeautifulSoup, parser: PageParser, amount: int
    ) -> NewsCollection | None:
        """This method will get the news using the given parser.

        Args:
            soup (BeautifulSoup): The parsed HTML.
            parser (PageParser): A class that inherits from PageParser
            amount (int): The number of news entries to return

        Returns:
            list[dict[str, str]]: A list of dictionaries matching the Entry format

        """

        entries = parser.parse_entries(soup, amount)
        if entries:
            logger.info(
                f"Extracted {len(entries.entries)} entries from {parser.__class__.__name__}"
            )
        return entries
