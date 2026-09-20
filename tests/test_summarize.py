"""Tests for the Gemini summary service (finding 6)."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import NewsCollection, NewsEntry, Summary
from app.services import summarize

REPO_ROOT = Path(__file__).resolve().parents[1]

LOADING = "Summary is loading... Refresh in a few seconds!"
FAILED = "Could not generate summary at this time."
EMPTY = "No summary available at this time."
NO_ARTICLES = "No articles available to summarize."


def make_collection(count: int = 2) -> NewsCollection:
    return NewsCollection(
        entries=[
            NewsEntry(
                title=f"Title {index}",
                content=f"Content {index}",
                source="Nation",
                link=f"https://example.com/{index}",
                date_scraped="2026-09-20",
            )
            for index in range(count)
        ]
    )


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.get_entries = AsyncMock(return_value=make_collection())
    fake.get_summary = AsyncMock(return_value=None)
    fake.test_and_set = AsyncMock(return_value=True)
    fake.release_lock = AsyncMock()
    fake.add_summary = AsyncMock()
    monkeypatch.setattr(summarize, "db_client", fake)
    return fake


@pytest.fixture
def genai_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.aio.models.generate_content = AsyncMock(
        return_value=MagicMock(text="A summary")
    )
    monkeypatch.setattr(summarize, "get_client", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_happy_path_uses_async_client_caches_and_releases(
    db: MagicMock, genai_client: MagicMock
) -> None:
    result = await summarize.summarize_latest_news()

    assert result == "A summary"
    generate = genai_client.aio.models.generate_content
    generate.assert_awaited_once()
    assert generate.call_args.kwargs["model"]
    assert "Title 0" in generate.call_args.kwargs["contents"]
    assert "Content 1" in generate.call_args.kwargs["contents"]
    db.add_summary.assert_awaited_once()
    assert db.add_summary.call_args.args[1] == "A summary"
    db.release_lock.assert_awaited_once()
    # The synchronous client surface must never be used inside the event loop.
    genai_client.models.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_generate_failure_releases_lock_and_returns_fallback(
    db: MagicMock, genai_client: MagicMock
) -> None:
    genai_client.aio.models.generate_content.side_effect = RuntimeError("boom")

    result = await summarize.summarize_latest_news()

    assert result == FAILED
    db.release_lock.assert_awaited_once()
    db.add_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_creation_failure_releases_lock(
    db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_client() -> MagicMock:
        raise ValueError("Missing key")

    monkeypatch.setattr(summarize, "get_client", broken_client)

    result = await summarize.summarize_latest_news()

    assert result == FAILED
    db.release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_released_even_when_caching_raises(
    db: MagicMock, genai_client: MagicMock
) -> None:
    db.add_summary.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await summarize.summarize_latest_news()

    db.release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_not_acquired_skips_genai(
    db: MagicMock, genai_client: MagicMock
) -> None:
    db.test_and_set.return_value = False

    result = await summarize.summarize_latest_news()

    assert result == LOADING
    genai_client.aio.models.generate_content.assert_not_awaited()
    db.release_lock.assert_not_awaited()
    db.add_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_summary_short_circuits_before_lock(
    db: MagicMock, genai_client: MagicMock
) -> None:
    db.get_summary.return_value = Summary(title_hash="abc", ai_summary="cached")

    result = await summarize.summarize_latest_news()

    assert result == "cached"
    db.test_and_set.assert_not_awaited()
    db.release_lock.assert_not_awaited()
    genai_client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_articles(db: MagicMock, genai_client: MagicMock) -> None:
    db.get_entries.return_value = None

    assert await summarize.summarize_latest_news() == NO_ARTICLES

    db.test_and_set.assert_not_awaited()
    genai_client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_response_is_not_cached(
    db: MagicMock, genai_client: MagicMock
) -> None:
    genai_client.aio.models.generate_content.return_value = MagicMock(text="")

    result = await summarize.summarize_latest_news()

    assert result == EMPTY
    db.add_summary.assert_not_awaited()
    db.release_lock.assert_awaited_once()


def test_get_client_is_lazy_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_cls = MagicMock(return_value=sentinel)
    monkeypatch.setattr(summarize, "_client", None)
    monkeypatch.setattr(summarize.genai, "Client", fake_cls)

    assert summarize.get_client() is sentinel
    assert summarize.get_client() is sentinel
    fake_cls.assert_called_once()


def test_module_imports_without_gemini_api_key() -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.setdefault("MONGODB_URL", "mongodb://localhost:27017")

    completed = subprocess.run(
        [sys.executable, "-c", "import app.services.summarize"],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
