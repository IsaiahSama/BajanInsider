import re
from datetime import UTC, datetime, timedelta
from os import getenv
from typing import Any, override

from bson.objectid import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.collation import Collation
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.models import NewsCollection, NewsEntry, Summary
from app.models.last_updated import LastUpdated
from app.services.logger import get_logger

from .db_client import DBClient

logger = get_logger(__name__)

# A news entry's identity is enforced by two unique indexes (see `ensure_indexes`):
#   1. the article URL: the same story re-seen on a later day, or re-headlined,
#      still has the same link;
#   2. (title, source), compared case-insensitively: catches aggregator copies
#      whose link is a redirect rather than the publisher's URL.
# `date_scraped` is deliberately not part of the identity. Feeds keep items for
# days, and the old (title, source, date_scraped) key stored them once per day.
NEWS_LINK_INDEX_NAME = "uniq_link"
NEWS_LINK_INDEX_KEYS: list[tuple[str, int]] = [("link", ASCENDING)]
NEWS_TITLE_SOURCE_INDEX_NAME = "uniq_title_source"
NEWS_TITLE_SOURCE_INDEX_KEYS: list[tuple[str, int]] = [
    ("title", ASCENDING),
    ("source", ASCENDING),
]
CASE_INSENSITIVE = Collation(locale="en", strength=2)
"""Collation for the (title, source) index and its lookups: ignores case and accents."""
LEGACY_INDEX_NAMES: tuple[str, ...] = ("uniq_title_source_date",)
"""Indexes from earlier identities; `ensure_indexes` drops any still present."""
DUPLICATE_KEY_ERROR_CODE = 11000


def _fold(text: str) -> str:
    """Approximates the index collation in Python: case- and whitespace-insensitive."""
    return " ".join(text.split()).casefold()


def _identity_keys(entry: NewsEntry) -> tuple[str, tuple[str, str]]:
    """The two keys that identify an entry, mirroring the unique indexes."""
    return entry.link, (_fold(entry.title), _fold(entry.source))


SEARCH_MAX_LENGTH = 100
"""Longest search string passed to `$regex`; longer input is truncated."""

SORT_DATE: dict[str, Any] = {
    "$ifNull": [
        "$published_at",
        "$created_at",
        {
            "$dateFromString": {
                "dateString": "$date_scraped",
                "onError": None,
                "onNull": None,
            }
        },
    ]
}
"""When an entry was published, as far as we know: the feed's own timestamp, else
when we stored it, else the day it was scraped (rows that predate `created_at`)."""

NEWEST_FIRST: dict[str, int] = {"_sort_date": DESCENDING, "created_at": DESCENDING}
"""Feed order: by `SORT_DATE`, then by insertion time for entries sharing a date."""


def _newest_first(
    match: dict[str, Any], *, skip: int = 0, limit: int
) -> list[dict[str, Any]]:
    """An aggregation pipeline returning `match`ing entries newest first.

    The sort key is computed per document because older rows lack `published_at`
    (and the oldest lack `created_at`); `$ifNull` picks the best date each has.
    """
    pipeline: list[dict[str, Any]] = [
        {"$match": match},
        {"$addFields": {"_sort_date": SORT_DATE}},
        {"$sort": NEWEST_FIRST},
    ]
    if skip:
        pipeline.append({"$skip": skip})
    pipeline += [{"$limit": limit}, {"$unset": "_sort_date"}]
    return pipeline


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

    @override
    async def ensure_indexes(self) -> None:
        existing = await self.news_db.index_information()
        for legacy in LEGACY_INDEX_NAMES:
            if legacy in existing:
                await self.news_db.drop_index(legacy)
                logger.info(f"Dropped legacy index {legacy!r} on {self.news_table}")

        link_index = await self.news_db.create_index(
            NEWS_LINK_INDEX_KEYS, name=NEWS_LINK_INDEX_NAME, unique=True
        )
        pair_index = await self.news_db.create_index(
            NEWS_TITLE_SOURCE_INDEX_KEYS,
            name=NEWS_TITLE_SOURCE_INDEX_NAME,
            unique=True,
            collation=CASE_INSENSITIVE,
        )
        logger.info(
            f"Ensured unique indexes {link_index!r} and {pair_index!r} "
            f"on {self.news_table}"
        )

    async def is_unique_entry(self, entry: NewsEntry) -> bool:
        """Checks whether no stored entry shares this entry's identity.

        Args:
            entry (NewsEntry): The entry to look up.

        Returns:
            bool: True if no document has the same link, nor the same
                (title, source) ignoring case.
        """
        return not bool(
            await self.news_db.find_one(
                {
                    "$or": [
                        {"link": entry.link},
                        {"title": entry.title, "source": entry.source},
                    ]
                },
                collation=CASE_INSENSITIVE,
            )
        )

    @override
    async def add_news_entry(self, news_entry: NewsEntry) -> NewsEntry | None:
        if not await self.is_unique_entry(news_entry):
            return None

        try:
            new_entry = await self.news_db.insert_one(
                news_entry.model_dump(by_alias=True, exclude={"id"})
            )
        except DuplicateKeyError:
            # Lost a race with another writer between the check and the insert;
            # the unique index has the final say.
            logger.info(
                f"Skipped duplicate entry {news_entry.title!r} from {news_entry.source}"
            )
            return None

        return await self.get_entry(new_entry.inserted_id)

    @override
    async def add_news_entries(self, news_collection: NewsCollection) -> int:
        # Dedupe within the batch first. The unique index would reject the second
        # copy anyway, but this keeps it out of the request and the logs.
        docs: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()
        for entry in news_collection.entries:
            link, pair = _identity_keys(entry)
            if link in seen_links or pair in seen_pairs:
                continue
            seen_links.add(link)
            seen_pairs.add(pair)
            docs.append(entry.model_dump(by_alias=True, exclude={"id"}))

        in_batch_duplicates = len(news_collection.entries) - len(docs)

        if not docs:
            logger.info("No news entries to insert")
            return 0

        # ordered=False makes the server attempt every document and report the
        # rejected ones together, instead of stopping at the first duplicate.
        skipped_existing = 0
        backfilled = 0
        try:
            result = await self.news_db.insert_many(docs, ordered=False)
            inserted = len(result.inserted_ids)
        except BulkWriteError as error:
            details = error.details or {}
            write_errors: list[dict[str, Any]] = details.get("writeErrors", [])
            other_errors = [
                (e.get("index"), e.get("code"), e.get("errmsg"))
                for e in write_errors
                if e.get("code") != DUPLICATE_KEY_ERROR_CODE
            ]
            if other_errors:
                logger.error(
                    f"Bulk insert into {self.news_table} failed with "
                    f"{len(other_errors)} non-duplicate write error(s) "
                    f"(index, code, errmsg): {other_errors}"
                )
                raise

            skipped_existing = len(write_errors)
            inserted = int(details.get("nInserted", 0))
            rejected = [
                docs[e["index"]]
                for e in write_errors
                if isinstance(e.get("index"), int)
            ]
            backfilled = await self._backfill_empty_copies(rejected)

        logger.info(
            f"Bulk insert into {self.news_table}: inserted={inserted} "
            f"skipped_duplicates={in_batch_duplicates + skipped_existing} "
            f"(in_batch={in_batch_duplicates}, already_stored={skipped_existing}) "
            f"backfilled={backfilled}"
        )
        return inserted

    async def _backfill_empty_copies(self, rejected: list[dict[str, Any]]) -> int:
        """Gives stored copies without a snippet the content of a rejected duplicate.

        An aggregator's copy stored earlier has an empty snippet and a redirect
        link. When the outlet's own copy arrives later and is rejected as a
        duplicate, its snippet, link and publish time are copied onto the stored
        document instead of being thrown away.

        Args:
            rejected (list[dict[str, Any]]): The documents the bulk insert rejected.

        Returns:
            int: How many stored documents were filled in.
        """
        filled = 0
        for doc in rejected:
            if not doc["content"].strip():
                continue
            same_story_without_snippet = {
                "$or": [
                    {"link": doc["link"]},
                    {"title": doc["title"], "source": doc["source"]},
                ],
                "content": "",
            }
            fields: dict[str, Any] = {"content": doc["content"], "link": doc["link"]}
            if doc.get("published_at") is not None:
                fields["published_at"] = doc["published_at"]
            try:
                result = await self.news_db.update_one(
                    same_story_without_snippet,
                    {"$set": fields},
                    collation=CASE_INSENSITIVE,
                )
            except DuplicateKeyError:
                # The outlet's link is already on another stored copy; keep the
                # stored link and still fill in the snippet.
                del fields["link"]
                result = await self.news_db.update_one(
                    same_story_without_snippet,
                    {"$set": fields},
                    collation=CASE_INSENSITIVE,
                )
            filled += int(result.modified_count > 0)
        return filled

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

        cursor = self.news_db.aggregate(_newest_first(query, limit=100))
        results: list[NewsEntry] = []

        for collection in await cursor.to_list(100):
            if collection:
                collection: dict[str, Any]
                results.append(NewsEntry(**collection))

        return NewsCollection(entries=results) if results else None

    @override
    async def get_entries(
        self, start: int = 0, limit: int = 50
    ) -> NewsCollection | None:
        entries = await self.news_db.aggregate(
            _newest_first({}, skip=start, limit=limit)
        ).to_list(limit)

        if entries:
            entries: list[dict[str, Any]]
            return NewsCollection(entries=[NewsEntry(**entry) for entry in entries])

    @override
    async def get_all_entries(self) -> NewsCollection | None:
        entries: list[dict[str, Any]] = await self.news_db.aggregate(
            _newest_first({}, limit=1000)
        ).to_list(1000)

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
