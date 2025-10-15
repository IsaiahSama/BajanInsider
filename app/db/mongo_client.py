from pymongo import DESCENDING

from os import getenv
from typing import Any, override

from bson.objectid import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from app.models.last_updated import LastUpdated
from app.services.create_tags import create_tags

from .db_client import DBClient
from app.models import NewsEntry, NewsCollection, Summary


class MongoClient(DBClient):
    """
    This class represents a connection to the Mongo Database
    """

    client: AsyncIOMotorClient[Any]

    db_name: str = "BajanInsiderMongoDB"
    news_table: str = "news_entry"
    last_updated_table: str = "last_updated"
    summary_cache_table: str = "summary_cache"

    db: AsyncIOMotorDatabase[Any]
    news_db: AsyncIOMotorCollection[dict[str, str]]
    last_updated_db: AsyncIOMotorCollection[dict[str, str]]
    summary_cache_db: AsyncIOMotorCollection[dict[str, str]]

    def __init__(self):
        self.connect()

    @override
    def connect(self):
        self.client = AsyncIOMotorClient(getenv("MONGODB_URL"))

        self.db = self.client.get_database(self.db_name)

        self.news_db = self.db.get_collection(self.news_table)
        self.last_updated_db = self.db.get_collection(self.last_updated_table)
        self.summary_cache_db = self.db.get_collection(self.summary_cache_table)

    async def is_unique_title(self, title: str) -> bool:
        return not bool(await self.news_db.find_one({"title": title}))

    @override
    async def add_news_entry(self, news_entry: NewsEntry) -> NewsEntry | None:
        if not await self.is_unique_title(news_entry.title):
            return None

        new_entry = await self.news_db.insert_one(
            news_entry.model_dump(by_alias=True, exclude={"id"})
        )

        created_entry = await self.get_entry(new_entry.inserted_id)

        return created_entry

    @override
    async def add_news_entries(self, news_collection: NewsCollection) -> None:
        entries: list[dict[str, str]] = []
        
        for entry in news_collection.entries:
            if await self.is_unique_title(entry.title):
                entry.tags = await create_tags(entry.title, entry.content)
                entries.append(entry.model_dump(by_alias=True, exclude={"id"}))
        
        entries: list[dict[str, str]] = [
            entry.model_dump(by_alias=True, exclude={"id"})
            for entry in news_collection.entries
            if await self.is_unique_title(entry.title)
        ]

        if not entries:
            return

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
    async def find_entry(self, search: str) -> NewsCollection | None:
        query = {
            "$or": [
                {"title": {"$regex": search, "$options": "i"}},
                {"content": {"$regex": search, "$options": "i"}},
            ]
        }

        cursor = self.news_db.find(query)
        results: list[NewsEntry] = []

        for collection in await cursor.sort("date_scraped", DESCENDING).to_list(100):
            if collection:
                results.append(NewsEntry(**collection))

        return NewsCollection(entries=results) if results else None

    @override
    async def get_entries(
        self, start: int = 0, limit: int = 50
    ) -> NewsCollection | None:
        entries = (
            await self.news_db.find()
            .sort("date_scraped", DESCENDING)
            .skip(start)
            .limit(limit)
            .to_list(limit)
        )

        if entries:
            return NewsCollection(entries=[NewsEntry(**entry) for entry in entries])

    @override
    async def get_all_entries(self) -> NewsCollection | None:
        entries = (
            await self.news_db.find().sort("date_scraped", DESCENDING).to_list(1000)
        )

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
        
    @override
    async def get_summary(self, title_hash: str) -> Summary | None:
        summary = await self.summary_cache_db.find_one({"title_hash": title_hash})

        if not summary:
            return None

        return Summary(**summary)
    
    @override
    async def add_summary(self, title_hash: str, summary_text: str) -> Summary:
        existing_summary = await self.get_summary(title_hash)

        if existing_summary:
            return existing_summary

        new_summary = Summary(title_hash=title_hash, ai_summary=summary_text)
        _ = await self.summary_cache_db.insert_one(
            new_summary.model_dump(exclude={"id"})
        )
        return new_summary

client = MongoClient()