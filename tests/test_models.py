"""Tests for the pydantic models (findings 4 and 7b)."""

import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models import last_updated as last_updated_module
from app.models.last_updated import LastUpdated
from app.models.news_entry import NewsEntry


def make_entry(**overrides: object) -> NewsEntry:
    data: dict[str, object] = {
        "title": "Title",
        "content": "Content",
        "source": "Nation",
        "link": "https://example.com/a",
        "date_scraped": "2026-09-20",
    }
    data.update(overrides)
    return NewsEntry(**data)  # pyright: ignore[reportArgumentType]


def test_identical_articles_are_equal_despite_id_and_created_at() -> None:
    a = make_entry(
        _id="64f000000000000000000001",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    b = make_entry(
        _id="64f000000000000000000002",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_default_created_at_does_not_break_equality() -> None:
    a = make_entry()
    b = make_entry()

    assert a == b
    assert len({a, b}) == 1


def test_different_link_is_not_equal() -> None:
    a = make_entry()
    b = make_entry(link="https://example.com/b")

    assert a != b
    assert len({a, b}) == 2


def test_different_title_or_source_is_not_equal() -> None:
    base = make_entry()

    assert base != make_entry(title="Other")
    assert base != make_entry(source="Advocate")


def test_content_is_not_part_of_identity() -> None:
    a = make_entry(content="first version")
    b = make_entry(content="updated version")

    assert a == b
    assert len({a, b}) == 1


def test_entry_is_not_equal_to_other_types() -> None:
    assert make_entry() != "not an entry"
    assert make_entry() != {"title": "Title"}


def test_entry_is_frozen() -> None:
    entry = make_entry()

    with pytest.raises(ValidationError):
        entry.title = "changed"  # pyright: ignore[reportAttributeAccessIssue]


def test_created_at_default_is_timezone_aware_utc() -> None:
    entry = make_entry()

    assert entry.created_at.tzinfo is not None
    assert entry.created_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - entry.created_at) < timedelta(seconds=5)


def test_id_alias_and_populate_by_name() -> None:
    oid = ObjectId()

    by_alias = make_entry(_id=oid)
    by_name = make_entry(id=str(oid))

    assert by_alias.id == str(oid)
    assert by_name.id == str(oid)
    assert by_alias.model_dump(by_alias=True)["_id"] == str(oid)
    assert "id" not in by_alias.model_dump(by_alias=True)


def test_last_updated_default_is_evaluated_per_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDatetime:
        current = datetime(2001, 2, 3, 12, 0, tzinfo=UTC)

        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return cls.current if tz is None else cls.current.astimezone(tz)

    monkeypatch.setattr(last_updated_module, "datetime", FakeDatetime)

    first = LastUpdated()
    FakeDatetime.current = datetime(2004, 5, 6, 12, 0, tzinfo=UTC)
    second = LastUpdated()

    assert first.last_updated == "2001-02-03"
    assert second.last_updated == "2004-05-06"


def test_last_updated_default_is_today() -> None:
    expected = datetime.now().astimezone().strftime("%Y-%m-%d")

    assert LastUpdated().last_updated == expected
