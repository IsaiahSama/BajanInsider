"""This will store the base class, and subclasses for Page parsers!"""

from datetime import datetime
from typing import override
from bs4 import BeautifulSoup


class PageParser:
    url: str = ""  # The URL for the page

    @staticmethod
    def parse_entries(soup: BeautifulSoup, n: int) -> list[dict[str, str]] | None:
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
    def parse_entries(soup: BeautifulSoup, n: int) -> list[dict[str, str]] | None:
        entries: list[dict[str, str]] = []
        # Meta Information

        # CSS Selector Pattern

        # rso > div > div > div:nth-child(1) > div > div > a > div > div.SoAPf
        # rso > div > div > div:nth-child(2) > div > div > a > div > div.SoAPf
        # rso > div > div > div:nth-child(3) > div > div > a > div > div.SoAPf

        link_selector_base = "# rso > div > div > div:nth-child({}) > div > div > a"

        base_selector = "> div > div.SoAPf > "

        index = 1
        title_selector_base = "div.n0jPhd.ynAwRc.MBeuO.nDgy9d"
        source_name_selector_base = "div:nth-child(1) > div.MgUUmf.NUnG9d > span"
        content_selector_base = "div.GI74Re.nDgy9d"

        for _ in range(n):
            link_selector = link_selector_base.format(index)
            root_selector = link_selector + base_selector
            title_selector = root_selector + title_selector_base
            source_name_selector = root_selector + source_name_selector_base
            content_selector = root_selector + content_selector_base

            title = soup.css.select_one(title_selector).text
            content = soup.css.select_one(content_selector).text
            source = soup.css.select_one(source_name_selector).text
            link = soup.css.select_one(link_selector).text
            date_scraped = datetime.now()

            entry = {
                "title": title,
                "content": content,
                "sourceName": source,
                "sourceLink": link,
                "dateScraped": date_scraped,
            }

            index += 1
            entries.append(entry)

        # Data Filtering

        # Return
        return entries
