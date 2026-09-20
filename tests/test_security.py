"""Tests for output escaping in the HTMX news feed (findings 1 and 9)."""

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

EVIL_TITLE = "<script>alert(1)</script>"
EVIL_CONTENT = "<img src=x onerror=alert(2)>"
EVIL_LINK = "javascript:alert(1)"


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


def evil_entry() -> NewsEntry:
    return make_entry(
        title=EVIL_TITLE, content=EVIL_CONTENT, link=EVIL_LINK, source="<b>src</b>"
    )


@pytest.fixture
def http() -> TestClient:
    # No context manager on purpose: the startup hook rewrites public/sitemap.xml.
    return TestClient(main.app)


@pytest.fixture
def entries(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    get_entries = AsyncMock(return_value=NewsCollection(entries=[evil_entry()]))
    monkeypatch.setattr(main.client, "get_entries", get_entries)
    monkeypatch.setattr(main.client, "count_entries", AsyncMock(return_value=1))
    return get_entries


def test_render_partial_helper_is_gone() -> None:
    assert not hasattr(main, "render_partial")


def test_scraped_html_is_escaped_in_feed(http: TestClient, entries: AsyncMock) -> None:
    response = http.get("/htmx/entries")

    assert response.status_code == 200
    body = response.text
    assert EVIL_TITLE not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert EVIL_CONTENT not in body
    assert "&lt;img src=x onerror=alert(2)&gt;" in body
    assert "<b>src</b>" not in body
    assert "&lt;b&gt;src&lt;/b&gt;" in body


def test_javascript_links_are_not_clickable(
    http: TestClient, entries: AsyncMock
) -> None:
    body = http.get("/htmx/entries").text

    assert 'href="javascript:' not in body
    assert EVIL_LINK not in body
    # The card still tells the reader where the article came from.
    assert "Read full article on" in body


def test_http_links_are_rendered_and_attribute_escaped(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = 'https://example.com/story?a=1&b=2"onmouseover="alert(1)'
    monkeypatch.setattr(
        main.client,
        "get_entries",
        AsyncMock(return_value=NewsCollection(entries=[make_entry(link=link)])),
    )
    monkeypatch.setattr(main.client, "count_entries", AsyncMock(return_value=1))

    body = http.get("/htmx/entries").text

    assert (
        'href="https://example.com/story?a=1&amp;b=2&#34;onmouseover=&#34;alert(1)"'
        in body
    )
    assert 'onmouseover="alert(1)"' not in body


@pytest.mark.parametrize("link", ["http://example.com/a", "https://example.com/a"])
def test_plain_http_and_https_links_are_allowed(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    monkeypatch.setattr(
        main.client,
        "get_entries",
        AsyncMock(return_value=NewsCollection(entries=[make_entry(link=link)])),
    )
    monkeypatch.setattr(main.client, "count_entries", AsyncMock(return_value=1))

    assert f'href="{link}"' in http.get("/htmx/entries").text


@pytest.mark.parametrize(
    "link", ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://x", "//evil"]
)
def test_non_http_links_are_dropped(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    monkeypatch.setattr(
        main.client,
        "get_entries",
        AsyncMock(return_value=NewsCollection(entries=[make_entry(link=link)])),
    )
    monkeypatch.setattr(main.client, "count_entries", AsyncMock(return_value=1))

    assert "href=" not in http.get("/htmx/entries").text


def test_filtered_feed_is_escaped_too(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main.client,
        "find_entry",
        AsyncMock(return_value=NewsCollection(entries=[evil_entry()])),
    )

    response = http.post("/htmx/entries/filter", data={"search": "alert"})

    assert response.status_code == 200
    assert EVIL_TITLE not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert 'href="javascript:' not in response.text


def test_search_term_is_escaped_in_pagination(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    many = NewsCollection(
        entries=[make_entry(link=f"https://example.com/{i}") for i in range(31)]
    )
    monkeypatch.setattr(main.client, "find_entry", AsyncMock(return_value=many))
    evil_search = '"><script>alert(1)</script>'

    body = http.post("/htmx/entries/filter", data={"search": evil_search}).text

    assert evil_search not in body
    assert "<script>alert(1)</script>" not in body
    # JSON for hx-vals is emitted via `tojson`, which escapes angle brackets.
    assert "\\u003cscript\\u003e" in body
    assert 'hx-post="/htmx/entries/filter?page=2"' in body
