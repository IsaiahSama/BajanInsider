"""This file handles the scraping logic for the news sources

This has been repurposed from the original"""

from bs4 import BeautifulSoup
from requests import get

from app.models.news_collection import NewsCollection

from .page_parser import PageParser

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
    def get_soup(url: str) -> BeautifulSoup:
        """Retrieves the beautiful Soup from the webpage

        Args:
            url (str): The url of the page to get and turn into Soup

        Returns:
            BeautifulSoup: The soup object"""

        page = get(url)
        page.raise_for_status()

        return BeautifulSoup(page.text, "html.parser")

    @staticmethod
    def get_news(
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
        return entries
