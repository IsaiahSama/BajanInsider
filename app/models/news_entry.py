from datetime import UTC, datetime
from typing import Annotated, override

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


def utc_now() -> datetime:
    """Returns the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class NewsEntry(BaseModel, frozen=True):
    """
    Model representing a news entry.

    Two entries are the same article when their `title`, `source` and `link`
    match. `id`, `content`, `published_at` and `created_at` are left out of
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
