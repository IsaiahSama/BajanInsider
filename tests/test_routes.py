"""Tests for the HTMX feed routes, pagination and static files (findings 8-11)."""

import os
from pathlib import Path

os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test")

# The app currently resolves `templates/` and `public/` relative to the CWD.
APP_DIR = Path(__file__).resolve().parents[1] / "app"
if not (Path.cwd() / "public").is_dir():
    os.chdir(APP_DIR)

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import NewsCollection, NewsEntry


def make_entry(index: int = 0) -> NewsEntry:
    return NewsEntry(
        title=f"Title {index}",
        content="Content",
        source="Nation",
        link=f"https://example.com/{index}",
        date_scraped="2026-09-20",
    )


def make_collection(count: int) -> NewsCollection:
    return NewsCollection(entries=[make_entry(i) for i in range(count)])


@pytest.fixture
def http() -> TestClient:
    # No context manager on purpose: the startup hook rewrites public/sitemap.xml.
    return TestClient(main.app, follow_redirects=False)


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        "count_entries": AsyncMock(return_value=95),
        "get_entries": AsyncMock(return_value=make_collection(30)),
        "get_all_entries": AsyncMock(return_value=make_collection(95)),
        "find_entry": AsyncMock(return_value=make_collection(31)),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(main.client, name, mock)
    return mocks


def test_feed_counts_with_count_entries_not_get_all_entries(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    response = http.get("/htmx/entries?page=2")

    assert response.status_code == 200
    feed["count_entries"].assert_awaited_once()
    feed["get_all_entries"].assert_not_awaited()
    feed["get_entries"].assert_awaited_once_with(30, 30)

    body = response.text
    assert body.count("<article") == 30
    assert 'data-total-pages="4"' in body
    assert 'data-current-page="2"' in body
    assert 'hx-get="/htmx/entries?page=1"' in body
    assert 'hx-get="/htmx/entries?page=3"' in body
    assert 'hx-post="' not in body


def test_pagination_processes_dynamically_created_buttons(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    body = http.get("/htmx/entries").text

    assert "htmx.process(" in body


def test_filter_route_has_no_trailing_slash_redirect(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    response = http.post("/htmx/entries/filter", data={"search": "title"})

    assert response.status_code == 200


def test_filtered_pagination_keeps_the_search_term(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    body = http.post("/htmx/entries/filter", data={"search": "bridgetown"}).text

    assert body.count("<article") == 30
    assert 'data-total-pages="2"' in body
    assert 'data-search="bridgetown"' in body
    assert 'hx-post="/htmx/entries/filter?page=2"' in body
    assert '{"search": "bridgetown"}' in body
    assert 'hx-get="/htmx/entries?page=2"' not in body


def test_filtered_second_page_slices_and_links_back(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    body = http.post("/htmx/entries/filter?page=2", data={"search": "bridgetown"}).text

    assert body.count("<article") == 1
    assert "Title 30" in body
    assert 'hx-post="/htmx/entries/filter?page=1"' in body
    assert 'hx-get="/htmx/entries?page=1"' not in body


def test_empty_search_falls_back_to_unfiltered_feed(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    response = http.post("/htmx/entries/filter", data={"search": ""})

    # An empty required Form() field is a 422 in FastAPI; the route must default it.
    assert response.status_code == 200
    feed["find_entry"].assert_not_awaited()
    feed["get_entries"].assert_awaited_once()
    assert 'data-search=""' in response.text


def test_filter_with_no_results_shows_empty_state(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    feed["find_entry"].return_value = None

    response = http.post("/htmx/entries/filter", data={"search": "zzz"})

    assert response.status_code == 200
    assert "No News Found" in response.text


def test_empty_feed_shows_empty_state(
    http: TestClient, feed: dict[str, AsyncMock]
) -> None:
    feed["count_entries"].return_value = 0
    feed["get_entries"].return_value = None

    response = http.get("/htmx/entries")

    assert response.status_code == 200
    assert "No News Found" in response.text


def test_robots_txt_is_served_at_root(http: TestClient) -> None:
    response = http.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == (APP_DIR / "public" / "robots.txt").read_text()


def test_sitemap_xml_is_served_at_root(http: TestClient) -> None:
    response = http.get("/sitemap.xml")

    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    assert "<urlset" in response.text
