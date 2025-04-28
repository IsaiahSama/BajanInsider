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
        """This method will handle the setup for establishing a connection for the database.
        The `client` variable is provided to keep a handle on the created client
        """
        raise NotImplementedError

    @abstractmethod
    async def add_news_entry(self, news_entry: NewsEntry) -> NewsEntry | None:
        """Adds a news entry to the database.

        Args:
            news_entry (NewsEntry): The entry to serialize and add to the database

        Returns:
            NewsEntry: The created NewsEntry
            None: If insertion failed
        """
        raise NotImplementedError

    @abstractmethod
    async def add_news_entries(self, news_collection: NewsCollection) -> None:
        """Adds a collection of news entries to the database. To be used as a bulk operation.

        Args:
            news_collection (NewsCollection): The collection of NewsEntry to be added.

        Returns:
            None
        """
        raise NotImplementedError

    @abstractmethod
    async def get_entry(self, entry_id: str) -> NewsEntry | None:
        """Queries the database to get a NewsEntry by ID

        Args:
            entry_id (str): The ID of the news entry to request.

        Returns:
            NewsEntry: The found NewsEntry
            None: If no entry was found
        """
        raise NotImplementedError

    @abstractmethod
    async def find_entry(self, search: str) -> NewsCollection | None:
        """Queries the database for all NewsEntry objects matching the query.

        Args:
            search (str): A string representing a search term to be found within the title or content.

        Returns:
            NewsCollection: The collection if found.
            None: If no entries match the query.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_all_entries(self) -> NewsCollection | None:
        """Queries the database to get all news entries as a collection.

        Returns:
            NewsCollection: All found entries.
            None: If no entries were found.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_last_updated_date(self) -> LastUpdated | None:
        """Sets a 'last_updated' date in the database.
        This is used to determine whether or not to run the scraping scripts.
        Scraping should only be run once a day.
        This function is intended to be called if `get_last_updated_date` returns nothing.

        Returns:
            LastUpdated: The newly created object
            None: If the insertion operation failed
        """
        raise NotImplementedError

    @abstractmethod
    async def get_last_updated_date(self) -> LastUpdated | None:
        """Retrieves the LastUpdated date from the database.
        This can be used to determine the last time the scraping was run.

        Returns:
            LastUpdated: An object representing the last date the script was run
        """
        raise NotImplementedError

    @abstractmethod
    async def update_last_updated_date(self) -> None:
        """Updates the last updated date with the current date using the %Y-%m-%d format"""
        raise NotImplementedError
