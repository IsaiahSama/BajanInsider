"""Tests for MongoClient query helpers (findings 2, 3, 7a and 11)."""

import re
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import bson
import pytest
from pymongo import DESCENDING

from app.db.mongo_client import SEARCH_MAX_LENGTH, MongoClient

# Newest first by the publisher's own timestamp, falling back to when we stored
# the entry, and for the oldest rows (no created_at) to the scrape date.
EXPECTED_SORT = {"_sort_date": DESCENDING, "created_at": DESCENDING}
EXPECTED_SORT_DATE = {
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
    cursor.to_list = AsyncMock(return_value=docs)
    return cursor


def pipeline_of(news_db: MagicMock) -> list[dict[str, Any]]:
    news_db.aggregate.assert_called_once()
    return news_db.aggregate.call_args.args[0]


def stage(pipeline: list[dict[str, Any]], name: str) -> Any:
    matches = [s[name] for s in pipeline if name in s]
    assert len(matches) == 1, f"expected exactly one {name} stage, got {matches}"
    return matches[0]


def assert_newest_first(pipeline: list[dict[str, Any]]) -> None:
    assert stage(pipeline, "$addFields") == {"_sort_date": EXPECTED_SORT_DATE}
    assert stage(pipeline, "$sort") == EXPECTED_SORT
    assert pipeline.index(
        next(s for s in pipeline if "$addFields" in s)
    ) < pipeline.index(next(s for s in pipeline if "$sort" in s))
    assert stage(pipeline, "$unset") == "_sort_date"


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
):
    news_db.aggregate.return_value = make_cursor([])

    await db.find_entry("(a+)+$")

    for clause in regex_clauses(stage(pipeline_of(news_db), "$match")):
        assert clause["$regex"] == re.escape("(a+)+$")
        assert clause["$options"] == "i"


@pytest.mark.asyncio
async def test_find_entry_searches_title_and_content(
    db: MongoClient, news_db: MagicMock
):
    news_db.aggregate.return_value = make_cursor([])

    await db.find_entry("bridgetown")

    query = stage(pipeline_of(news_db), "$match")
    assert sorted(field for clause in query["$or"] for field in clause) == [
        "content",
        "title",
    ]


@pytest.mark.asyncio
async def test_find_entry_caps_search_length(db: MongoClient, news_db: MagicMock):
    news_db.aggregate.return_value = make_cursor([])

    await db.find_entry("x" * (SEARCH_MAX_LENGTH + 50))

    for clause in regex_clauses(stage(pipeline_of(news_db), "$match")):
        assert clause["$regex"] == "x" * SEARCH_MAX_LENGTH


@pytest.mark.asyncio
async def test_find_entry_orders_newest_first_with_date_fallback(
    db: MongoClient, news_db: MagicMock
):
    news_db.aggregate.return_value = make_cursor([make_doc(0)])

    await db.find_entry("anything")

    pipeline = pipeline_of(news_db)
    assert_newest_first(pipeline)
    assert stage(pipeline, "$limit") == 100


@pytest.mark.asyncio
async def test_find_entry_returns_none_when_nothing_matches(
    db: MongoClient, news_db: MagicMock
):
    news_db.aggregate.return_value = make_cursor([])

    assert await db.find_entry("nothing") is None


@pytest.mark.asyncio
async def test_get_entries_orders_newest_first_and_paginates(
    db: MongoClient, news_db: MagicMock
):
    news_db.aggregate.return_value = make_cursor([make_doc(0)])

    result = await db.get_entries(60, 30)

    pipeline = pipeline_of(news_db)
    assert_newest_first(pipeline)
    assert stage(pipeline, "$skip") == 60
    assert stage(pipeline, "$limit") == 30
    assert pipeline.index(next(s for s in pipeline if "$sort" in s)) < pipeline.index(
        next(s for s in pipeline if "$skip" in s)
    )
    assert result is not None and len(result.entries) == 1


@pytest.mark.asyncio
async def test_get_all_entries_orders_newest_first(db: MongoClient, news_db: MagicMock):
    news_db.aggregate.return_value = make_cursor([make_doc(0), make_doc(1)])

    result = await db.get_all_entries()

    assert_newest_first(pipeline_of(news_db))
    assert result is not None and len(result.entries) == 2


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
