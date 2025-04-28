from abc import ABC, abstractmethod
from typing import Any

from app.models import NewsEntry, NewsCollection, LastUpdated


class DBClient(ABC):
    """
    This represents a client that connects to a Database.
    This class is meant to be inherited from
    """

    client: Any
    db_name: str
    news_table: str = "news_entry"
    last_updated_table: str = "last_updated"

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def add_news_entry(self, news_entry: NewsEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    async def add_news_entries(self, news_collection: NewsCollection) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_entry(self, entry_id: str) -> NewsEntry:
        raise NotImplementedError

    @abstractmethod
    async def get_all_entries(self) -> NewsCollection:
        raise NotImplementedError

    @abstractmethod
    async def create_last_updated_date(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_last_updated_date(self) -> LastUpdated:
        raise NotImplementedError

    @abstractmethod
    async def update_last_updated_date(self) -> None:
        raise NotImplementedError
