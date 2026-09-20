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

from .db_client import DBClient
from app.models import NewsEntry, NewsCollection, Summary

import re
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

SEARCH_MAX_LENGTH = 100
"""Longest search string passed to `$regex`; longer input is truncated."""

NEWEST_FIRST: list[tuple[str, int]] = [
    ("created_at", DESCENDING),
    ("date_scraped", DESCENDING),
]
"""Sort order for feeds. Passed as one list: chaining `.sort()` calls replaces the previous key."""

LOCK_ID = "summary_lock"
"""`_id` of the single document that acts as the summary-generation lock."""

LOCK_STALE_SECONDS = 120
"""A held lock older than this is treated as abandoned and may be re-acquired."""


class MongoClient(DBClient):
    """
    This class represents a connection to the Mongo Database
    """

    client: AsyncIOMotorClient[Any]

    db_name: str = "BajanInsiderMongoDB"
    news_table: str = "news_entry"
    last_updated_table: str = "last_updated"
    test_set_table: str = "test_set"
    summary_cache_table: str = "summary_cache"

    db: AsyncIOMotorDatabase[Any]
    news_db: AsyncIOMotorCollection[dict[str, str]]
    last_updated_db: AsyncIOMotorCollection[dict[str, str]]
    test_set_db: AsyncIOMotorCollection[dict[str, str]]
    summary_cache_db: AsyncIOMotorCollection[dict[str, str]]

    def __init__(self):
        self.connect()

    @override
    def connect(self):
        self.client = AsyncIOMotorClient(getenv("MONGODB_URL"))

        self.db = self.client.get_database(self.db_name)

        self.news_db = self.db.get_collection(self.news_table)
        self.last_updated_db = self.db.get_collection(self.last_updated_table)
        self.test_set_db = self.db.get_collection(self.test_set_table)
        self.summary_cache_db = self.db.get_collection(self.summary_cache_table)

    async def is_unique_entry(self, entry: NewsEntry) -> bool:
        return not bool(
            await self.news_db.find_one(
                {
                    "title": entry.title,
                    "source": entry.source,
                    "date_scraped": entry.date_scraped,
                }
            )
        )

    @override
    async def add_news_entry(self, news_entry: NewsEntry) -> NewsEntry | None:
        if not await self.is_unique_entry(news_entry):
            return None

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
            if await self.is_unique_entry(entry)
        ]

        if not entries:
            return

        _ = await self.news_db.insert_many(entries)

    @override
    async def get_entry(self, entry_id: str | ObjectId) -> NewsEntry | None:
        if isinstance(entry_id, str):
            entry_id = ObjectId(entry_id)

        entry: dict[str, Any] | None = await self.news_db.find_one({"_id": entry_id})

        if not entry:
            return None

        news_entry = NewsEntry(**entry)
        return news_entry

    @override
    async def find_entry(self, search: str) -> NewsCollection | None:
        # Match the user's text literally. Unescaped input such as `(a+)+$`
        # makes the regex engine backtrack for a very long time, and the search
        # box fires on every keystroke.
        pattern = re.escape(search[:SEARCH_MAX_LENGTH])
        query = {
            "$or": [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"content": {"$regex": pattern, "$options": "i"}},
            ]
        }

        cursor = self.news_db.find(query)
        results: list[NewsEntry] = []

        for collection in await cursor.sort(NEWEST_FIRST).to_list(100):
            if collection:
                collection: dict[str, Any]
                results.append(NewsEntry(**collection))

        return NewsCollection(entries=results) if results else None

    @override
    async def get_entries(
        self, start: int = 0, limit: int = 50
    ) -> NewsCollection | None:
        entries = (
            await self.news_db.find()
            .sort(NEWEST_FIRST)
            .skip(start)
            .limit(limit)
            .to_list(limit)
        )

        if entries:
            entries: list[dict[str, Any]]
            return NewsCollection(entries=[NewsEntry(**entry) for entry in entries])

    @override
    async def get_all_entries(self) -> NewsCollection | None:
        entries: list[dict[str, Any]] = (
            await self.news_db.find().sort(NEWEST_FIRST).to_list(1000)
        )

        return (
            NewsCollection(entries=[NewsEntry(**entry) for entry in entries])
            if entries
            else None
        )

    @override
    async def count_entries(self) -> int:
        return await self.news_db.count_documents({})

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
        _ = await self.last_updated_db.update_one(
            {},
            {"$set": {"last_updated": LastUpdated().last_updated}},
            upsert=True,
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

    @override
    async def test_and_set(self) -> bool:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=LOCK_STALE_SECONDS)

        # One find-and-modify is atomic on the server, so two concurrent callers
        # cannot both see the lock as free. If the document exists but is held
        # and fresh, the filter does not match and the upsert collides with the
        # existing `_id`, which surfaces as DuplicateKeyError.
        try:
            lock = await self.test_set_db.find_one_and_update(
                {
                    "_id": LOCK_ID,
                    "$or": [
                        {"locked": False},
                        {"acquired_at": {"$lt": stale_before}},
                    ],
                },
                {"$set": {"locked": True, "acquired_at": now}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return False

        return lock is not None

    @override
    async def release_lock(self) -> None:
        _ = await self.test_set_db.update_one(
            {"_id": LOCK_ID}, {"$set": {"locked": False}}, upsert=True
        )


client = MongoClient()

