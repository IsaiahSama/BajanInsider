"""Shared fixtures for the BajanInsider test-suite.

The environment is prepared here, before anything under ``app`` is imported:
``app/__init__.py`` loads ``app/.env`` (absent in CI), ``app.db.mongo_client``
builds the Mongo client from ``MONGODB_URL`` at import time, and
``app.services.summarize`` builds a ``genai.Client`` that needs
``GEMINI_API_KEY``. No Mongo server is required: tests that reach the database
use the ``mock_db`` fixture, which replaces the singleton's async methods.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

from app.models import NewsCollection, NewsEntry  # noqa: E402  (needs env above)

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_ORIGINAL_CWD = Path.cwd()


def pytest_configure(config: pytest.Config) -> None:
    """TEMPORARY: runs the suite from ``app/`` so that ``app.main`` can be imported.

    ``app.main`` currently resolves ``public`` and ``templates`` relative to the
    current working directory, so the application only imports with CWD=app/.
    The paths are being anchored to the package in a parallel change; once that
    has landed this hook and ``pytest_unconfigure`` can be deleted.

    It is a hook rather than module-level code because pytest globs
    ``testpaths`` against the CWD *after* loading this conftest; it still runs
    before any test module is imported.
    """
    if not Path("public").is_dir() and (_APP_DIR / "public").is_dir():
        os.chdir(_APP_DIR)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restores the working directory changed by ``pytest_configure``."""
    os.chdir(_ORIGINAL_CWD)


@pytest.fixture
def sample_entry() -> NewsEntry:
    """A single news entry used as the default database content."""
    return NewsEntry(
        title="Test headline: Barbados unveils new fixture",
        content="A short snippet of the story body used by the tests.",
        source="Test Source",
        link="https://example.com/story",
        date_scraped="2026-09-20",
    )


@pytest.fixture
def sample_collection(sample_entry: NewsEntry) -> NewsCollection:
    """A collection holding just ``sample_entry``."""
    return NewsCollection(entries=[sample_entry])


@pytest.fixture
def app() -> FastAPI:
    """The FastAPI application, imported lazily so the environment above applies."""
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """A synchronous test client for the application.

    The client is deliberately not used as a context manager, so startup and
    shutdown handlers do not run: today startup rewrites ``public/sitemap.xml``
    on disk, and it is about to start touching the database as well.
    """
    return TestClient(app)


@pytest.fixture
def mock_db(
    monkeypatch: pytest.MonkeyPatch, sample_collection: NewsCollection
) -> SimpleNamespace:
    """Replaces the database singleton's async methods with ``AsyncMock`` objects.

    Every method returns a sensible default: the read methods return
    ``sample_collection``, ``get_summary`` returns ``None`` (no cached summary)
    and ``test_and_set`` returns ``False`` (the lock is not acquired, so no call
    to Gemini is attempted). Methods that other work is still adding
    (``count_entries``, ``ensure_indexes``) are added to the singleton when they
    do not exist yet, so routes that start using them keep working.

    Returns:
        SimpleNamespace: The mocks, keyed by method name, so a test can tweak a
        return value or inspect calls, e.g.
        ``mock_db.get_summary.return_value = Summary(...)``.
    """
    from app import main as app_main

    db = app_main.client
    defaults: dict[str, object] = {
        "get_entries": sample_collection,
        "get_all_entries": sample_collection,
        "find_entry": sample_collection,
        "get_summary": None,
        "add_summary": None,
        "test_and_set": False,
        "release_lock": None,
        "count_entries": len(sample_collection.entries),
        "ensure_indexes": None,
    }

    mocks: dict[str, AsyncMock] = {}
    for name, return_value in defaults.items():
        mock = AsyncMock(return_value=return_value)
        # ``raising=False`` lets the not-yet-existing methods be added; monkeypatch
        # removes them again (and restores the real ones) after the test.
        monkeypatch.setattr(db, name, mock, raising=False)
        mocks[name] = mock

    return SimpleNamespace(**mocks)
