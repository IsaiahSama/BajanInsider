"""Tests for MongoClient query helpers (findings 2, 3, 7a and 11)."""

import re
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import bson
import pytest
from pymongo import DESCENDING

from app.db.mongo_client import SEARCH_MAX_LENGTH, MongoClient

EXPECTED_SORT = [("created_at", DESCENDING), ("date_scraped", DESCENDING)]


def make_doc(index: int = 0) -> dict[str, Any]:
    return {
        "_id": f"64f00000000000000000{index:04d}",
        "title": f"Title {index}",
        "content": "Content",
        "source": "Nation",
        "link": f"https://example.com/{index}",
        "date_scraped": "2026-09-20",
    }


def make_cursor(docs: list[dict[str, Any]]) -> MagicMock:
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


@pytest.fixture
def db() -> MongoClient:
    client = MongoClient()
    client.news_db = MagicMock()
    client.last_updated_db = MagicMock()
    return client


@pytest.fixture
def news_db(db: MongoClient) -> MagicMock:
    return cast(MagicMock, db.news_db)


@pytest.fixture
def last_updated_db(db: MongoClient) -> MagicMock:
    return cast(MagicMock, db.last_updated_db)


def regex_clauses(query: dict[str, Any]) -> list[dict[str, Any]]:
    return [clause[field] for clause in query["$or"] for field in clause]


@pytest.mark.asyncio
async def test_find_entry_escapes_regex_metacharacters(
    db: MongoClient, news_db: MagicMock
) -> None:
    news_db.find.return_value = make_cursor([])

    await db.find_entry("(a+)+$")

    query = news_db.find.call_args.args[0]
    clauses = regex_clauses(query)
    assert len(clauses) == 2
    for clause in clauses:
        assert clause["$regex"] == re.escape("(a+)+$")
        assert clause["$options"] == "i"


@pytest.mark.asyncio
async def test_find_entry_searches_title_and_content(
    db: MongoClient, news_db: MagicMock
) -> None:
    news_db.find.return_value = make_cursor([])

    await db.find_entry("bridgetown")

    query = news_db.find.call_args.args[0]
    fields = sorted(field for clause in query["$or"] for field in clause)
    assert fields == ["content", "title"]


@pytest.mark.asyncio
async def test_find_entry_caps_search_length(
    db: MongoClient, news_db: MagicMock
) -> None:
    news_db.find.return_value = make_cursor([])

    await db.find_entry("a" * (SEARCH_MAX_LENGTH + 50))

    query = news_db.find.call_args.args[0]
    for clause in regex_clauses(query):
        assert clause["$regex"] == re.escape("a" * SEARCH_MAX_LENGTH)


@pytest.mark.asyncio
async def test_find_entry_sorts_by_both_keys(
    db: MongoClient, news_db: MagicMock
) -> None:
    cursor = make_cursor([make_doc(1), make_doc(2)])
    news_db.find.return_value = cursor

    result = await db.find_entry("title")

    cursor.sort.assert_called_once_with(EXPECTED_SORT)
    assert result is not None
    assert [entry.title for entry in result.entries] == ["Title 1", "Title 2"]


@pytest.mark.asyncio
async def test_find_entry_returns_none_when_nothing_matches(
    db: MongoClient, news_db: MagicMock
) -> None:
    news_db.find.return_value = make_cursor([])

    assert await db.find_entry("nothing") is None


@pytest.mark.asyncio
async def test_get_entries_sorts_by_both_keys_and_paginates(
    db: MongoClient, news_db: MagicMock
) -> None:
    cursor = make_cursor([make_doc(1)])
    news_db.find.return_value = cursor

    result = await db.get_entries(30, 30)

    cursor.sort.assert_called_once_with(EXPECTED_SORT)
    cursor.skip.assert_called_once_with(30)
    cursor.limit.assert_called_once_with(30)
    cursor.to_list.assert_awaited_once_with(30)
    assert result is not None and len(result.entries) == 1


@pytest.mark.asyncio
async def test_get_all_entries_sorts_by_both_keys(
    db: MongoClient, news_db: MagicMock
) -> None:
    cursor = make_cursor([make_doc(1)])
    news_db.find.return_value = cursor

    result = await db.get_all_entries()

    cursor.sort.assert_called_once_with(EXPECTED_SORT)
    assert result is not None and len(result.entries) == 1


@pytest.mark.asyncio
async def test_count_entries_uses_count_documents(
    db: MongoClient, news_db: MagicMock
) -> None:
    news_db.count_documents = AsyncMock(return_value=42)

    assert await db.count_entries() == 42

    news_db.count_documents.assert_awaited_once_with({})


@pytest.mark.asyncio
async def test_update_last_updated_date_sets_today_with_upsert(
    db: MongoClient, last_updated_db: MagicMock
) -> None:
    last_updated_db.update_one = AsyncMock()

    await db.update_last_updated_date()

    last_updated_db.update_one.assert_awaited_once()
    args, kwargs = last_updated_db.update_one.call_args
    filt, update = args[0], args[1]

    assert filt == {}
    assert update == {
        "$set": {"last_updated": datetime.now().astimezone().strftime("%Y-%m-%d")}
    }
    assert kwargs["upsert"] is True
    # The original bug passed the LastUpdated class itself, which bson cannot encode.
    assert bson.BSON.encode(update)
