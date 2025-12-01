"""This will store the base class, and subclasses for Page parsers!"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import cast, override
from bs4 import BeautifulSoup, Tag
from bs4.element import PageElement

from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry


class PageParser(ABC):
    urls: list[str] = []  # The URLs to be used.

    @staticmethod
    @abstractmethod
    def parse_entries(soup: BeautifulSoup, n: int) -> NewsCollection | None:
        """This method will obtain news information from it's website.

        Args:
            soup (BeautifulSoup): The soup object representing the parsed webpage.
            n (int): The number of entries to obtain.

        Returns:
            dict: A mapping of the entires following the stated format.
        """
        raise NotImplementedError


class GoogleNewsParser(PageParser):
    urls: list[str] = [
        "https://www.google.com/search?&q=barbados+news&tbm=nws",
        "https://www.google.com/search?q=barbados+news&tbm=nws&start=10",
        "https://www.google.com/search?q=barbados+news&tbm=nws&start=20",
        "https://www.google.com/search?q=barbados+news&tbm=nws&start=30",
    ]

    @staticmethod
    @override
    def parse_entries(soup: BeautifulSoup, n: int) -> NewsCollection | None:
        entries: list[NewsEntry] = []
        # Meta Information

        # Containers with news have the CSS selector of:
        # #main > div > div > a

        news_container_selector = "#main > div > div > a"  # This gets 10 entries.

        news_containers: list[Tag] = soup.select(news_container_selector)

        for news_container in news_containers:
            a: Tag = news_container

            link: str = (
                a["href"].split("?")[1].lstrip("q=").split("&")[0]
            )  # href link is in format of: '/url?q=https://someurl/&someGoogleParams'

            if not isinstance(link, str):
                link = ""

            # Each container is split into two divs.
            inner_containers: list[Tag] = [
                child for child in news_container.contents if isinstance(child, Tag)
            ]

            if not inner_containers:
                continue

            # The first container contains the header information
            header_container: PageElement = inner_containers[0]

            # such as the title
            title_tag: Tag | None = header_container.select_one("div h3 div")
            title: str = cast(str, title_tag.text) if title_tag else "Unknown Title"

            # and source name
            source_tag: Tag | None = header_container.select("div > div")[-1]
            source: str = cast(str, source_tag.text) if source_tag else "Unknown Source"

            # The second container contains the body information
            body_container: PageElement = inner_containers[1]
            # such as the image, content, and date posted
            # Out of this, only the content is of relevance.

            # It is nested quite a bit, so will have to do some mining
            # There's only one nested span tag in here, containing text like "3 days ago"
            # We can get that, and then find the parent.

            span_tag: Tag | None = body_container.select_one("div span")
            # The parent of this span tag will be a div container with the content

            if not span_tag:
                continue

            content_tag = span_tag.find_parent()

            # Now we need to remove the span tag from the text.

            if content_tag and isinstance(content_tag, Tag) and content_tag.span:
                _ = content_tag.span.extract()

            # Finally, we can get the content by getting this text.

            content: str = cast(str, content_tag.text) if content_tag else ""

            date_scraped = datetime.now().strftime("%Y-%m-%d")

            entry = NewsEntry(
                title=title,
                content=content,
                source=source,
                link=link,
                date_scraped=date_scraped,
            )

            entries.append(entry)

        # Need to remove duplicates.
        entries = list(set(entries))

        news_collection = NewsCollection(entries=entries)
        # Return
        return news_collection
