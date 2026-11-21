"""Tests for the bulk-insert path and index management of ``MongoClient``.

The database is never touched: ``news_db`` is replaced with mocks so the tests
only assert on the calls the client makes.
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId
from pymongo import ASCENDING
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.db.mongo_client import (
    CASE_INSENSITIVE,
    LEGACY_INDEX_NAMES,
    NEWS_LINK_INDEX_NAME,
    NEWS_TITLE_SOURCE_INDEX_NAME,
    MongoClient,
)
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
    news_db.create_index = AsyncMock(side_effect=lambda keys, **kw: kw["name"])
    news_db.index_information = AsyncMock(return_value={"_id_": {}})
    news_db.drop_index = AsyncMock()
    news_db.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))
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
    # Same (title, source) but a different link/content is still the same
    # article: the secondary identity catches aggregator copies whose link is
    # a redirect rather than the publisher URL.
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
async def test_ensure_indexes_creates_link_and_title_source_indexes():
    client, news_db = make_client()

    await client.ensure_indexes()

    assert news_db.create_index.await_count == 2
    (link_args, link_kwargs), (pair_args, pair_kwargs) = [
        (call.args, call.kwargs) for call in news_db.create_index.await_args_list
    ]
    # Primary identity: the article URL.
    assert list(link_args[0]) == [("link", ASCENDING)]
    assert link_kwargs.get("unique") is True
    assert link_kwargs.get("name") == NEWS_LINK_INDEX_NAME == "uniq_link"
    # Secondary identity: headline + outlet, compared case-insensitively so
    # "BBC News"/"bbc news" and re-capitalised headlines collapse.
    assert list(pair_args[0]) == [("title", ASCENDING), ("source", ASCENDING)]
    assert pair_kwargs.get("unique") is True
    assert (
        pair_kwargs.get("name") == NEWS_TITLE_SOURCE_INDEX_NAME == "uniq_title_source"
    )
    assert pair_kwargs.get("collation") is CASE_INSENSITIVE
    assert CASE_INSENSITIVE.document == {"locale": "en", "strength": 2}
    news_db.drop_index.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_indexes_drops_the_legacy_date_index_when_present():
    client, news_db = make_client()
    news_db.index_information.return_value = {"_id_": {}, "uniq_title_source_date": {}}

    await client.ensure_indexes()

    assert "uniq_title_source_date" in LEGACY_INDEX_NAMES
    news_db.drop_index.assert_awaited_once_with("uniq_title_source_date")


@pytest.mark.asyncio
async def test_add_news_entries_dedupes_same_link_regardless_of_title():
    client, news_db = make_client()
    first = make_entry("Original headline")
    re_headlined = NewsEntry(
        title="Updated headline",
        content="",
        source="Nation News",
        link=first.link,
        date_scraped="2026-09-21",
    )

    await client.add_news_entries(NewsCollection(entries=[first, re_headlined]))

    (docs,), _ = news_db.insert_many.await_args
    assert [doc["title"] for doc in docs] == ["Original headline"]


@pytest.mark.asyncio
async def test_add_news_entries_dedupes_title_and_source_case_insensitively():
    client, news_db = make_client()
    own_feed = NewsEntry(
        title="Sugar arrangement in limbo",
        content="",
        source="BBC News",
        link="https://www.bbc.co.uk/news/articles/abc",
        date_scraped="2026-09-20",
    )
    via_aggregator = NewsEntry(
        title="SUGAR ARRANGEMENT IN LIMBO",
        content="",
        source="bbc news",
        link="https://news.google.com/rss/articles/xyz",
        date_scraped="2026-09-20",
    )

    await client.add_news_entries(NewsCollection(entries=[own_feed, via_aggregator]))

    (docs,), _ = news_db.insert_many.await_args
    assert [doc["link"] for doc in docs] == ["https://www.bbc.co.uk/news/articles/abc"]


@pytest.mark.asyncio
async def test_add_news_entries_treats_same_story_seen_on_another_day_as_duplicate():
    client, news_db = make_client()
    monday = make_entry("Same story", date="2026-09-20")
    tuesday = NewsEntry(
        title="Same story",
        content="",
        source="Nation News",
        link="https://example.com/republished",
        date_scraped="2026-09-21",
    )

    await client.add_news_entries(NewsCollection(entries=[monday, tuesday]))

    (docs,), _ = news_db.insert_many.await_args
    assert len(docs) == 1


@pytest.mark.asyncio
async def test_add_news_entries_keeps_the_same_headline_from_different_outlets():
    """Title alone is NOT identity: two outlets' own articles under one headline stay."""
    client, news_db = make_client()
    nation = make_entry("Barbados installs second president", source="Nation News")
    observer = NewsEntry(
        title="Barbados installs second president",
        content="",
        source="Jamaica Observer",
        link="https://www.jamaicaobserver.com/2025/12/01/barbados-president/",
        date_scraped="2026-09-20",
    )

    await client.add_news_entries(NewsCollection(entries=[nation, observer]))

    (docs,), _ = news_db.insert_many.await_args
    assert [doc["source"] for doc in docs] == ["Nation News", "Jamaica Observer"]


@pytest.mark.asyncio
async def test_is_unique_entry_matches_on_link_or_title_and_source():
    client, news_db = make_client()
    entry = make_entry("Existing")

    assert await client.is_unique_entry(entry) is True

    news_db.find_one.assert_awaited_once()
    args, kwargs = news_db.find_one.await_args
    assert args[0] == {
        "$or": [
            {"link": entry.link},
            {"title": entry.title, "source": entry.source},
        ]
    }
    assert kwargs.get("collation") is CASE_INSENSITIVE


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


def publisher_copy() -> NewsEntry:
    return NewsEntry(
        title="Sugar arrangement in limbo",
        content="A real snippet from the outlet's own feed.",
        source="Barbados Today",
        link="https://barbadostoday.bb/2026/09/20/sugar-arrangement-in-limbo/",
        date_scraped="2026-09-20",
        published_at=datetime(2026, 9, 20, 9, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_rejected_duplicate_with_content_backfills_an_empty_stored_copy():
    """A Google copy stored earlier has no snippet; the outlet's copy fills it in."""
    client, news_db = make_client()
    publisher = publisher_copy()
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )

    inserted = await client.add_news_entries(NewsCollection(entries=[publisher]))

    assert inserted == 0
    news_db.update_one.assert_awaited_once()
    (filter_, update), kwargs = news_db.update_one.await_args
    assert filter_ == {
        "$or": [
            {"link": publisher.link},
            {"title": publisher.title, "source": publisher.source},
        ],
        "content": "",
    }
    assert update == {
        "$set": {
            "content": publisher.content,
            "link": publisher.link,
            "published_at": publisher.published_at,
        }
    }
    assert kwargs.get("collation") is CASE_INSENSITIVE


@pytest.mark.asyncio
async def test_rejected_duplicate_without_content_leaves_the_stored_copy_alone():
    client, news_db = make_client()
    google_copy = NewsEntry(
        title="Sugar arrangement in limbo",
        content="",
        source="Barbados Today",
        link="https://news.google.com/rss/articles/abc",
        date_scraped="2026-09-20",
    )
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )

    await client.add_news_entries(NewsCollection(entries=[google_copy]))

    news_db.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_keeps_the_stored_link_when_the_publisher_link_is_taken():
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )
    news_db.update_one.side_effect = [
        DuplicateKeyError("uniq_link"),
        SimpleNamespace(modified_count=1),
    ]

    await client.add_news_entries(NewsCollection(entries=[publisher_copy()]))

    assert news_db.update_one.await_count == 2
    (_, retry_update), _ = news_db.update_one.await_args_list[1]
    assert "link" not in retry_update["$set"]
    assert retry_update["$set"]["content"] == publisher_copy().content


@pytest.mark.asyncio
async def test_backfill_count_is_logged(caplog):
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await client.add_news_entries(NewsCollection(entries=[publisher_copy()]))

    assert "backfilled=1" in caplog.text


@pytest.mark.asyncio
async def test_rejected_duplicate_without_content_still_backfills_a_missing_publish_date():
    """An aggregator copy brings no snippet but does bring the publisher's date;
    a stored copy that has neither snippet nor date should at least get the date."""
    client, news_db = make_client()
    google_copy = NewsEntry(
        title="Sugar arrangement in limbo",
        content="",
        source="Barbados Today",
        link="https://news.google.com/rss/articles/abc",
        date_scraped="2026-09-20",
        published_at=datetime(2026, 9, 19, 8, tzinfo=UTC),
    )
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )

    await client.add_news_entries(NewsCollection(entries=[google_copy]))

    news_db.update_one.assert_awaited_once()
    (filter_, update), kwargs = news_db.update_one.await_args
    assert filter_ == {
        "$or": [
            {"link": google_copy.link},
            {"title": google_copy.title, "source": google_copy.source},
        ],
        "published_at": None,
    }
    assert update == {"$set": {"published_at": google_copy.published_at}}
    assert kwargs.get("collation") is CASE_INSENSITIVE


@pytest.mark.asyncio
async def test_publish_date_is_not_backfilled_again_when_the_snippet_update_set_it():
    """The snippet backfill already writes published_at; no second write follows."""
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )

    await client.add_news_entries(NewsCollection(entries=[publisher_copy()]))

    news_db.update_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_date_is_backfilled_when_the_stored_copy_already_had_a_snippet():
    """Stored copy has content (so the snippet update matches nothing) but no
    date; the rejected outlet copy's date is still written."""
    client, news_db = make_client()
    news_db.insert_many.side_effect = bulk_write_error(
        [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}], 0
    )
    news_db.update_one.side_effect = [
        SimpleNamespace(modified_count=0),  # nothing without a snippet to fill
        SimpleNamespace(modified_count=1),  # but the date was missing
    ]

    await client.add_news_entries(NewsCollection(entries=[publisher_copy()]))

    assert news_db.update_one.await_count == 2
    (filter_, update), _ = news_db.update_one.await_args_list[1]
    assert filter_["published_at"] is None
    assert update == {"$set": {"published_at": publisher_copy().published_at}}


# Aggregator batches: one wire story re-surfaced under several outlets.

WIRE_TITLE = "'It shows what it means': Mayo footballer skips Barbados holiday"


def google_copy_from(source: str, n: int = 0, title: str = WIRE_TITLE) -> NewsEntry:
    return NewsEntry(
        title=title,
        content="",
        source=source,
        link=f"https://news.google.com/rss/articles/{source.replace(' ', '')}{n}",
        date_scraped="2026-11-20",
    )


def stored_titles(news_db: MagicMock, titles: list[str]) -> None:
    """Makes `news_db.find(...).to_list()` return documents with these titles."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"title": t} for t in titles])
    news_db.find = MagicMock(return_value=cursor)


def inserted_docs(news_db: MagicMock) -> list[dict]:
    return news_db.insert_many.await_args.args[0]


@pytest.mark.asyncio
async def test_aggregator_batch_keeps_one_copy_of_a_title_across_sources():
    client, news_db = make_client()
    stored_titles(news_db, [])
    irish_times = google_copy_from("The Irish Times")
    breaking = google_copy_from("BreakingNews.ie")

    await client.add_news_entries(
        NewsCollection(entries=[irish_times, breaking]), aggregator=True
    )

    assert [d["source"] for d in inserted_docs(news_db)] == ["The Irish Times"]


@pytest.mark.asyncio
async def test_aggregator_title_match_ignores_case_and_spacing():
    client, news_db = make_client()
    stored_titles(news_db, [])
    first = google_copy_from("The Irish Times")
    shouted = google_copy_from("BreakingNews.ie", title=f"  {WIRE_TITLE.upper()} ")

    await client.add_news_entries(
        NewsCollection(entries=[first, shouted]), aggregator=True
    )

    assert len(inserted_docs(news_db)) == 1


@pytest.mark.asyncio
async def test_aggregator_entry_is_dropped_when_the_title_is_already_stored():
    client, news_db = make_client()
    stored_titles(news_db, [WIRE_TITLE.lower()])
    fresh = google_copy_from("Barbados Today", title="Market vendors struggle")

    await client.add_news_entries(
        NewsCollection(entries=[google_copy_from("BreakingNews.ie"), fresh]),
        aggregator=True,
    )

    (query, _), kwargs = news_db.find.call_args
    assert query == {"title": {"$in": [WIRE_TITLE, "Market vendors struggle"]}}
    assert kwargs.get("collation") is CASE_INSENSITIVE
    assert [d["title"] for d in inserted_docs(news_db)] == ["Market vendors struggle"]


@pytest.mark.asyncio
async def test_aggregator_batch_of_only_stored_titles_inserts_nothing():
    client, news_db = make_client()
    stored_titles(news_db, [WIRE_TITLE])

    inserted = await client.add_news_entries(
        NewsCollection(entries=[google_copy_from("BreakingNews.ie")]), aggregator=True
    )

    assert inserted == 0
    news_db.insert_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_title_dropped_aggregator_copy_still_backfills_a_publish_date():
    client, news_db = make_client()
    stored_titles(news_db, [WIRE_TITLE])
    dated = google_copy_from("The Irish Times").model_copy(
        update={"published_at": datetime(2026, 11, 20, 6, tzinfo=UTC)}
    )

    await client.add_news_entries(NewsCollection(entries=[dated]), aggregator=True)

    news_db.update_one.assert_awaited_once()
    (filter_, update), _ = news_db.update_one.await_args
    assert filter_["published_at"] is None
    assert update == {"$set": {"published_at": dated.published_at}}


@pytest.mark.asyncio
async def test_outlet_batches_still_keep_same_headline_from_different_sources():
    """Title alone is not an outlet's identity: two papers' own articles may share it."""
    client, news_db = make_client()
    stored_titles(news_db, [WIRE_TITLE])
    nation = make_entry(WIRE_TITLE, source="Nation News")
    today = make_entry(WIRE_TITLE, source="Barbados Today")
    today = today.model_copy(update={"link": "https://barbadostoday.bb/x"})

    await client.add_news_entries(NewsCollection(entries=[nation, today]))

    news_db.find.assert_not_called()
    assert len(inserted_docs(news_db)) == 2
