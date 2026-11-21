"""Tests for the publisher favicon shown beside each story's source."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import NewsCollection, NewsEntry
from app.services.page_parser import BarbadosTodayParser, GoogleNewsRSSParser

FIXTURES = Path(__file__).parent / "fixtures"
GOOGLE_LINK = "https://news.google.com/rss/articles/ABC?oc=5"


def make_entry(**overrides: object) -> NewsEntry:
    data: dict[str, object] = {
        "title": "Title",
        "content": "Content",
        "source": "Nation",
        "link": "https://www.nationnews.com/2026/09/20/story/",
        "date_scraped": "2026-09-20",
    }
    data.update(overrides)
    return NewsEntry(**data)  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- model


def test_first_party_entry_uses_its_link_host() -> None:
    entry = make_entry()

    assert entry.source_domain == "nationnews.com"
    assert entry.favicon_url == (
        "https://www.google.com/s2/favicons?sz=64&domain=nationnews.com"
    )


def test_source_url_wins_over_an_aggregator_link() -> None:
    entry = make_entry(link=GOOGLE_LINK, source_url="https://www.bbc.co.uk")

    assert entry.source_domain == "bbc.co.uk"


def test_aggregator_link_without_source_url_has_no_favicon() -> None:
    entry = make_entry(link=GOOGLE_LINK)

    assert entry.source_domain is None
    assert entry.favicon_url is None


@pytest.mark.parametrize(
    "link", ["javascript:alert(1)", "data:text/html,x", "not a url", ""]
)
def test_non_web_links_have_no_favicon(link: str) -> None:
    assert make_entry(link=link).favicon_url is None


def test_source_url_does_not_affect_equality() -> None:
    assert make_entry(source_url="https://a.test") == make_entry()


# --------------------------------------------------------------------------- parsers


def test_google_entries_keep_the_publisher_site() -> None:
    text = (FIXTURES / "googlenews.xml").read_text(encoding="utf-8")
    collection = GoogleNewsRSSParser.parse_entries(text, 200)
    assert collection is not None

    by_source = {entry.source: entry for entry in collection.entries}
    assert by_source["The Guardian"].source_url == "https://www.theguardian.com"
    assert by_source["The Guardian"].source_domain == "theguardian.com"
    assert all(entry.favicon_url for entry in collection.entries)


def test_first_party_entries_store_no_source_url() -> None:
    text = (FIXTURES / "barbadostoday.xml").read_text(encoding="utf-8")
    collection = BarbadosTodayParser.parse_entries(text, 5)
    assert collection is not None

    for entry in collection.entries:
        assert entry.source_url is None
        assert entry.source_domain == "barbadostoday.bb"


def test_unsafe_source_url_is_dropped() -> None:
    entry = GoogleNewsRSSParser.build_entry(
        title="Story",
        link=GOOGLE_LINK,
        content="",
        base_url="",
        source="Someone",
        source_url="javascript:alert(1)",
    )
    assert entry is not None
    assert entry.source_url is None
    assert entry.favicon_url is None


# --------------------------------------------------------------------------- template


@pytest.fixture
def http() -> TestClient:
    # No context manager on purpose: the startup hook rewrites public/sitemap.xml.
    return TestClient(main.app)


def serve(monkeypatch: pytest.MonkeyPatch, *entries: NewsEntry) -> None:
    monkeypatch.setattr(
        main.client,
        "get_entries",
        AsyncMock(return_value=NewsCollection(entries=list(entries))),
    )
    monkeypatch.setattr(
        main.client, "count_entries", AsyncMock(return_value=len(entries))
    )


def test_card_shows_the_favicon(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve(monkeypatch, make_entry())

    body = http.get("/htmx/entries").text

    assert (
        '<img src="https://www.google.com/s2/favicons?sz=64&amp;domain=nationnews.com"'
        in body
    )


def test_card_without_a_known_site_has_no_image(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve(monkeypatch, make_entry(link=GOOGLE_LINK))

    assert "s2/favicons" not in http.get("/htmx/entries").text
