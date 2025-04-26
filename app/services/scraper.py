"""This file handles the scraping logic for the news sources

This has been repurposed from the original"""

from requests import get, post
from bs4 import BeautifulSoup
from datetime import datetime

from .page_parser import PageParser


class Scraper:
    def __init__(self):
        pass

    def get_soup(self, url: str) -> BeautifulSoup:
        """Retrieves the beautiful Soup from the webpage

        Args:
            url (str): The url of the page to get and turn into Soup

        Returns:
            BeautifulSoup: The soup object"""

        page = get(url)
        page.raise_for_status()

        return BeautifulSoup(page.text, "html.parser")

    def get_news(soup: BeautifulSoup, parser: PageParser) -> dict:
        pass
