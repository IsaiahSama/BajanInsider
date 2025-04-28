from os import getenv
from typing import Any, override

from bson.objectid import ObjectId
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

    client: AsyncIOMotorClient[Any]

    db_name: str = "BajanInsiderMongoDB"
    news_table: str = "news_entry"
    last_updated_table: str = "last_updated"

    db: AsyncIOMotorDatabase[Any]
    news_db: AsyncIOMotorCollection[dict[str, str]]
    last_updated_db: AsyncIOMotorCollection[dict[str, str]]

    def __init__(self):
        self.connect()

    @override
    def connect(self):
        self.client = AsyncIOMotorClient(getenv("MONGODB_URL"))

        self.db = self.client.get_database(self.db_name)

        self.news_db = self.db.get_collection(self.news_table)
        self.last_updated_db = self.db.get_collection(self.last_updated_table)

    @override
    async def add_news_entry(self, news_entry: NewsEntry) -> NewsEntry | None:
        new_entry = await self.news_db.insert_one(
            news_entry.model_dump(by_alias=True, exclude={"id"})
        )

        created_entry = await self.get_entry(new_entry.inserted_id)

        return created_entry

    @override
    async def add_news_entries(self, news_collection: NewsCollection) -> None:
        entries: list[dict[str, str]] = [
            entry.model_dump(by_alias=True, exclude={"id"})
            for entry in news_collection.entries
        ]

        _ = await self.news_db.insert_many(entries)

    @override
    async def get_entry(self, entry_id: str | ObjectId) -> NewsEntry | None:
        if isinstance(entry_id, str):
            entry_id = ObjectId(entry_id)

        entry: dict[str, str] | None = await self.news_db.find_one({"_id": entry_id})

        if not entry:
            return None

        news_entry = NewsEntry(**entry)
        return news_entry

    @override
    async def find_entry(self, query: dict[str, str]) -> NewsCollection | None:
        cursor = self.news_db.find(query)
        results: list[NewsEntry] = []

        for collection in await cursor.to_list(100):
            if collection:
                results.append(NewsEntry(**collection))

        return NewsCollection(entries=results) if results else None

    @override
    async def get_all_entries(self) -> NewsCollection | None:
        entries = await self.news_db.find().to_list(1000)

        return (
            NewsCollection(entries=[NewsEntry(**entry) for entry in entries])
            if entries
            else None
        )

    @override
    async def create_last_updated_date(self) -> LastUpdated | None:
        last_updated = LastUpdated()

        _ = await self.last_updated_db.insert_one(
            last_updated.model_dump(exclude={"id"})
        )

        found = await self.last_updated_db.find_one()
        return LastUpdated(**found) if found else None

    @override
    async def get_last_updated_date(self) -> LastUpdated | None:
        last_updated = await self.last_updated_db.find_one()

        if not last_updated:
            return await self.create_last_updated_date()

        return LastUpdated(**last_updated)

    @override
    async def update_last_updated_date(self) -> None:
        _ = await self.last_updated_db.find_one_and_update(
            filter={}, update={"$set": LastUpdated}
        )
