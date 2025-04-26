"""This will store the base class, and subclasses for Page parsers!"""

from typing import override
from bs4 import BeautifulSoup


class PageParser:
    url: str = ""  # The URL for the page

    @staticmethod
    def parse_entries(soup: BeautifulSoup, n: int) -> dict[str, str] | None:
        """This method will obtain news information from it's website.

        Args:
            soup (BeautifulSoup): The soup object representing the parsed webpage.
            n (int): The number of entries to obtain.

        Returns:
            dict: A mapping of the entires following the stated format.
        """

        pass


class GoogleNewsParser(PageParser):
    url: str = "https://www.google.com/search?&q=barbados+news&tbm=nws&source=lnms"

    @staticmethod
    @override
    def parse_entries(soup: BeautifulSoup, n: int) -> dict[str, str] | None:
        entries: dict[str, str] = {}
        # Meta Information

        # Data Filtering

        # Return
        return entries
