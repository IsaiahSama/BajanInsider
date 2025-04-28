from os import getenv
from typing import override

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from app.models.last_updated import LastUpdated

from .db_client import DBClient
from app.models import NewsEntry, NewsCollection


class MongoClient(DBClient):
    """
    This class represents a connection to the Mongo Database
    """

    client: AsyncIOMotorClient

    db_name: str = "BajanInsiderMongoDB"
    news_table: str = "news_entry"
    last_updated_table: str = "last_updated"

    db: AsyncIOMotorDatabase
    news_db: AsyncIOMotorCollection
    last_updated_db: AsyncIOMotorCollection

    def __init__(self):
        self.connect()

    @override
    def connect(self):
        self.client = AsyncIOMotorClient(getenv("MONGODB_URL"))

        self.db = self.client.get_database(self.db_name)

        self.news_db = self.db.get_collection(self.news_table)
        self.last_updated_db = self.db.get_collection(self.last_updated_table)

    @override
    def add_news_entry(self, news_entry: NewsEntry) -> None:
        raise NotImplementedError

    @override
    def add_news_entries(self, news_collection: NewsCollection) -> None:
        raise NotImplementedError

    @override
    def get_entry(self, entry_id: str) -> NewsEntry:
        raise NotImplementedError

    @override
    def get_all_entries(self) -> NewsCollection:
        raise NotImplementedError

    @override
    def create_last_updated_date(self) -> None:
        raise NotImplementedError

    @override
    def get_last_updated_date(self) -> LastUpdated:
        raise NotImplementedError

    @override
    def update_last_updated_date(self) -> None:
        raise NotImplementedError
