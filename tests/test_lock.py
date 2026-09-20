"""Tests for the atomic summary lock in MongoClient (finding 5)."""

import asyncio
import os

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db.mongo_client import LOCK_ID, LOCK_STALE_SECONDS, MongoClient


class FakeLockCollection:
    """A minimal in-memory stand-in for the lock collection.

    It implements just enough of `find_one_and_update` / `update_one` to
    reproduce MongoDB's semantics for the lock query: a filter that fails to
    match an existing `_id` and then upserts raises `DuplicateKeyError`.
    """

    def __init__(self, doc: dict[str, Any] | None = None) -> None:
        self.doc = doc

    def _matches(self, filt: dict[str, Any]) -> bool:
        if self.doc is None or self.doc["_id"] != filt["_id"]:
            return False

        for clause in filt["$or"]:
            if "locked" in clause and self.doc.get("locked") == clause["locked"]:
                return True
            if "acquired_at" in clause:
                acquired_at = self.doc.get("acquired_at")
                if (
                    acquired_at is not None
                    and acquired_at < clause["acquired_at"]["$lt"]
                ):
                    return True

        return False

    async def find_one_and_update(
        self,
        filt: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
        return_document: bool = ReturnDocument.BEFORE,
    ) -> dict[str, Any] | None:
        if self._matches(filt):
            assert self.doc is not None
            self.doc.update(update["$set"])
            return dict(self.doc)

        if not upsert:
            return None

        if self.doc is not None and self.doc["_id"] == filt["_id"]:
            raise DuplicateKeyError("E11000 duplicate key error")

        self.doc = {"_id": filt["_id"], **update["$set"]}
        return dict(self.doc) if return_document == ReturnDocument.AFTER else None

    async def update_one(
        self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> None:
        if self.doc is not None and self.doc["_id"] == filt["_id"]:
            self.doc.update(update["$set"])
        elif upsert:
            self.doc = {"_id": filt["_id"], **update["$set"]}


@pytest.fixture
def db() -> MongoClient:
    client = MongoClient()
    client.test_set_db = MagicMock()
    return client


def with_fake(db: MongoClient, doc: dict[str, Any] | None) -> FakeLockCollection:
    fake = FakeLockCollection(doc)
    db.test_set_db = fake  # pyright: ignore[reportAttributeAccessIssue]
    return fake


@pytest.mark.asyncio
async def test_acquire_issues_single_atomic_upsert(db: MongoClient) -> None:
    db.test_set_db.find_one_and_update = AsyncMock(
        return_value={"_id": LOCK_ID, "locked": True}
    )

    assert await db.test_and_set() is True

    db.test_set_db.find_one_and_update.assert_awaited_once()
    args, kwargs = db.test_set_db.find_one_and_update.call_args
    filt, update = args[0], args[1]

    assert filt["_id"] == LOCK_ID
    assert {"locked": False} in filt["$or"]
    stale_clause = next(c for c in filt["$or"] if "acquired_at" in c)
    cutoff = stale_clause["acquired_at"]["$lt"]
    age = datetime.now(UTC) - cutoff
    assert timedelta(seconds=LOCK_STALE_SECONDS - 5) < age
    assert age < timedelta(seconds=LOCK_STALE_SECONDS + 5)

    assert update["$set"]["locked"] is True
    assert isinstance(update["$set"]["acquired_at"], datetime)
    assert kwargs["upsert"] is True
    assert kwargs["return_document"] == ReturnDocument.AFTER


@pytest.mark.asyncio
async def test_returns_false_when_nothing_matched(db: MongoClient) -> None:
    db.test_set_db.find_one_and_update = AsyncMock(return_value=None)

    assert await db.test_and_set() is False


@pytest.mark.asyncio
async def test_duplicate_key_race_means_not_acquired(db: MongoClient) -> None:
    db.test_set_db.find_one_and_update = AsyncMock(
        side_effect=DuplicateKeyError("E11000 duplicate key error")
    )

    assert await db.test_and_set() is False


@pytest.mark.asyncio
async def test_acquires_when_no_lock_document_exists(db: MongoClient) -> None:
    fake = with_fake(db, None)

    assert await db.test_and_set() is True
    assert fake.doc is not None
    assert fake.doc["_id"] == LOCK_ID
    assert fake.doc["locked"] is True


@pytest.mark.asyncio
async def test_acquires_when_lock_is_free(db: MongoClient) -> None:
    fake = with_fake(
        db,
        {
            "_id": LOCK_ID,
            "locked": False,
            "acquired_at": datetime.now(UTC) - timedelta(seconds=1),
        },
    )

    assert await db.test_and_set() is True
    assert fake.doc is not None and fake.doc["locked"] is True


@pytest.mark.asyncio
async def test_does_not_acquire_when_lock_is_freshly_held(db: MongoClient) -> None:
    fake = with_fake(
        db,
        {
            "_id": LOCK_ID,
            "locked": True,
            "acquired_at": datetime.now(UTC) - timedelta(seconds=1),
        },
    )

    assert await db.test_and_set() is False
    assert fake.doc is not None and fake.doc["locked"] is True


@pytest.mark.asyncio
async def test_acquires_when_held_lock_is_stale(db: MongoClient) -> None:
    stale_time = datetime.now(UTC) - timedelta(seconds=LOCK_STALE_SECONDS + 60)
    fake = with_fake(db, {"_id": LOCK_ID, "locked": True, "acquired_at": stale_time})

    assert await db.test_and_set() is True
    assert fake.doc is not None
    assert fake.doc["acquired_at"] > stale_time


@pytest.mark.asyncio
async def test_release_then_reacquire_cycle(db: MongoClient) -> None:
    fake = with_fake(db, None)

    assert await db.test_and_set() is True
    assert await db.test_and_set() is False

    await db.release_lock()
    assert fake.doc is not None and fake.doc["locked"] is False

    assert await db.test_and_set() is True


@pytest.mark.asyncio
async def test_only_one_of_two_concurrent_callers_acquires(db: MongoClient) -> None:
    with_fake(db, None)

    results = await asyncio.gather(db.test_and_set(), db.test_and_set())

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_release_lock_clears_flag_with_upsert(db: MongoClient) -> None:
    db.test_set_db.update_one = AsyncMock()

    await db.release_lock()

    db.test_set_db.update_one.assert_awaited_once_with(
        {"_id": LOCK_ID}, {"$set": {"locked": False}}, upsert=True
    )
