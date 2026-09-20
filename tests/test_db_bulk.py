"""Tests for the bulk-insert path and index management of ``MongoClient``.

The database is never touched: ``news_db`` is replaced with mocks so the tests
only assert on the calls the client makes.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.db.mongo_client import NEWS_UNIQUE_INDEX_NAME, MongoClient
from app.models import NewsCollection, NewsEntry

LOGGER_NAME = "app.db.mongo_client"


def make_entry(
    title: str, source: str = "Nation News", date: str = "2026-09-20"
) -> NewsEntry:
    return NewsEntry(
        title=title,
        content=f"Content for {title}",
        source=source,
        link=f"https://example.com/{title.replace(' ', '-')}",
        date_scraped=date,
    )


def make_client() -> tuple[MongoClient, MagicMock]:
    """Builds a MongoClient whose news collection is fully mocked.

    Returns:
        tuple[MongoClient, MagicMock]: The client and the mock standing in for
        its ``news_db`` collection.
    """
    client = MongoClient()
    news_db = MagicMock()
    news_db.insert_many = AsyncMock(return_value=SimpleNamespace(inserted_ids=[]))
    news_db.insert_one = AsyncMock()
    news_db.find_one = AsyncMock(return_value=None)
    news_db.create_index = AsyncMock(return_value=NEWS_UNIQUE_INDEX_NAME)
    client.news_db = news_db
    return client, news_db


def bulk_write_error(write_errors: list[dict], n_inserted: int) -> BulkWriteError:
    return BulkWriteError(
        {
            "writeErrors": write_errors,
            "writeConcernErrors": [],
            "nInserted": n_inserted,
            "nUpserted": 0,
            "nMatched": 0,
            "nModified": 0,
            "nRemoved": 0,
            "upserted": [],
        }
    )


@pytest.mark.asyncio
async def test_add_news_entries_dedupes_within_batch_and_inserts_once():
    client, news_db = make_client()
    duplicate = make_entry("Same story")
    other = make_entry("Different story")
    # Same identity (title, source, date_scraped) but a different link/content
    # must still be treated as the same article.
    duplicate_variant = NewsEntry(
        title="Same story",
        content="Slightly different snippet",
        source="Nation News",
        link="https://example.com/other-link",
        date_scraped="2026-09-20",
    )
    news_db.insert_many.return_value = SimpleNamespace(
        inserted_ids=[ObjectId(), ObjectId()]
    )

    inserted = await client.add_news_entries(
        NewsCollection(entries=[duplicate, other, duplicate_variant])
    )

    news_db.insert_many.assert_awaited_once()
    args, kwargs = news_db.insert_many.await_args
    docs = args[0]
    assert kwargs.get("ordered") is False
    assert [doc["title"] for doc in docs] == ["Same story", "Different story"]
    assert all("_id" not in doc for doc in docs)
    # No per-entry uniqueness lookups any more.
    news_db.find_one.assert_not_awaited()
    assert inserted == 2


@pytest.mark.asyncio
async def test_add_news_entries_skips_duplicate_key_errors_without_raising(caplog):
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [
            {"index": 1, "code": 11000, "errmsg": "E11000 duplicate key error"},
            {"index": 2, "code": 11000, "errmsg": "E11000 duplicate key error"},
        ],
        n_inserted=1,
    )
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

    inserted = await client.add_news_entries(
        NewsCollection(entries=[make_entry("A"), make_entry("B"), make_entry("C")])
    )

    assert inserted == 1
    news_db.insert_many.assert_awaited_once()
    assert "inserted=1" in caplog.text
    assert "skipped_duplicates=2" in caplog.text
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.asyncio
async def test_add_news_entries_reraises_non_duplicate_write_errors(caplog):
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [
            {"index": 0, "code": 11000, "errmsg": "E11000 duplicate key error"},
            {"index": 1, "code": 121, "errmsg": "Document failed validation"},
        ],
        n_inserted=0,
    )
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

    with pytest.raises(BulkWriteError):
        await client.add_news_entries(
            NewsCollection(entries=[make_entry("A"), make_entry("B")])
        )

    assert any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.asyncio
async def test_add_news_entries_empty_batch_does_not_hit_the_database():
    client, news_db = make_client()

    inserted = await client.add_news_entries(NewsCollection(entries=[]))

    assert inserted == 0
    news_db.insert_many.assert_not_awaited()
    news_db.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_indexes_creates_unique_identity_index():
    client, news_db = make_client()

    await client.ensure_indexes()

    news_db.create_index.assert_awaited_once()
    args, kwargs = news_db.create_index.await_args
    assert list(args[0]) == [
        ("title", ASCENDING),
        ("source", ASCENDING),
        ("date_scraped", ASCENDING),
    ]
    assert kwargs.get("unique") is True
    assert kwargs.get("name") == NEWS_UNIQUE_INDEX_NAME == "uniq_title_source_date"


@pytest.mark.asyncio
async def test_add_news_entry_returns_none_for_existing_entry():
    client, news_db = make_client()
    entry = make_entry("Existing")
    news_db.find_one.return_value = {"_id": ObjectId(), "title": "Existing"}

    assert await client.add_news_entry(entry) is None
    news_db.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_news_entry_returns_none_on_duplicate_key_race():
    client, news_db = make_client()
    entry = make_entry("Raced")
    news_db.find_one.return_value = None
    news_db.insert_one.side_effect = DuplicateKeyError("E11000 duplicate key error")

    assert await client.add_news_entry(entry) is None


@pytest.mark.asyncio
async def test_add_news_entry_inserts_and_returns_created_entry():
    client, news_db = make_client()
    entry = make_entry("Fresh")
    new_id = ObjectId()
    stored = {"_id": new_id, **entry.model_dump(exclude={"id"})}
    # First find_one is the uniqueness check, the second is get_entry().
    news_db.find_one.side_effect = [None, stored]
    news_db.insert_one.return_value = SimpleNamespace(inserted_id=new_id)

    created = await client.add_news_entry(entry)

    assert created is not None
    assert created.id == str(new_id)
    assert created.title == "Fresh"
    news_db.insert_one.assert_awaited_once()
