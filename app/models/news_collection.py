from pydantic import BaseModel

from .news_entry import NewsEntry


class NewsCollection(BaseModel):
    """
    Class holding a list of `NewsEntry` instances.
    """

    entries: list[NewsEntry]
