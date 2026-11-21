from datetime import UTC, datetime
from typing import Annotated, override
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(str)]

FAVICON_SERVICE = "https://www.google.com/s2/favicons?sz=64&domain="
"""Resolves a domain to its favicon, so the site never fetches or stores icons itself."""

AGGREGATOR_HOSTS = frozenset({"news.google.com"})
"""Hosts whose links are redirects, not the publisher's own site."""


def utc_now() -> datetime:
    """Returns the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class NewsEntry(BaseModel, frozen=True):
    """
    Model representing a news entry.

    Two entries are the same article when their `title`, `source` and `link`
    match. `id`, `content`, `published_at`, `created_at` and `source_url` are left out of
    equality and hashing so that re-scraped articles deduplicate correctly.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    title: str
    content: str
    source: str
    link: str
    date_scraped: str
    published_at: datetime | None = None
    """When the publisher posted it, if the feed said; feeds are ordered by this."""
    created_at: datetime = Field(default_factory=utc_now)
    source_url: str | None = None
    """The publisher's site, when the link points elsewhere (an aggregator's redirect)."""

    @property
    def source_domain(self) -> str | None:
        """The publisher's host: from ``source_url``, else from ``link`` unless that is an aggregator."""
        for url in (self.source_url, self.link):
            if not url:
                continue
            parts = urlsplit(url)
            host = (parts.hostname or "").removeprefix("www.")
            if (
                parts.scheme in {"http", "https"}
                and host
                and host not in AGGREGATOR_HOSTS
            ):
                return host
        return None

    @property
    def favicon_url(self) -> str | None:
        """An icon for the publisher, or ``None`` when its site is unknown."""
        domain = self.source_domain
        return FAVICON_SERVICE + quote(domain, safe="") if domain else None

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NewsEntry):
            return NotImplemented

        return (self.title, self.source, self.link) == (
            other.title,
            other.source,
            other.link,
        )

    @override
    def __hash__(self) -> int:
        return hash((self.title, self.source, self.link))
