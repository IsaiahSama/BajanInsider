"""Tests for the per-source feed parsers, the snippet helpers, and the scrape orchestration.

Nothing here touches the network: every parser is fed a snapshot from ``tests/fixtures``.
``nationnews.xml``, ``barbadostoday.xml``, ``barbadostoday_atom.xml`` and ``bbc.xml`` are live
captures; ``advocate.xml`` is the last archived copy of a defunct feed (Wayback, 2016) and
``loopnews.xml`` is a labelled synthetic feed for a source that is currently offline.
"""

import re
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.models.news_collection import NewsCollection
from app.services import scrape
from app.services.page_parser import (
    BarbadosAdvocateParser,
    BarbadosTodayParser,
    BBCBarbadosParser,
    LoopNewsParser,
    NationNewsParser,
    PageParser,
    RSSParser,
    strip_html,
    truncate,
)
from app.services.scraper import Scraper

FIXTURES = Path(__file__).parent / "fixtures"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FIXTURE_FOR: dict[type[PageParser], str] = {
    NationNewsParser: "nationnews.xml",
    BarbadosTodayParser: "barbadostoday.xml",
    BBCBarbadosParser: "bbc.xml",
    LoopNewsParser: "loopnews.xml",
    BarbadosAdvocateParser: "advocate.xml",
}
ALL_PARSERS = list(FIXTURE_FOR)


def load(name: str) -> str:
    """Read a fixture file as text."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class ExampleFeedParser(RSSParser):
    """A bare RSS/Atom parser for the hand-written edge-case fixtures."""

    source_name: ClassVar[str] = "Example Feed"
    urls: ClassVar[list[str]] = ["https://example.test/feed/"]


# --------------------------------------------------------------------------- parsers


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.__name__)
def test_parser_returns_valid_entries(parser: type[PageParser]) -> None:
    collection = parser.parse_entries(load(FIXTURE_FOR[parser]), 50)

    assert isinstance(collection, NewsCollection)
    assert len(collection.entries) >= 5

    links = [entry.link for entry in collection.entries]
    assert len(links) == len(set(links)), "links must be unique within a parse"

    for entry in collection.entries:
        assert entry.title.strip(), "title must not be blank"
        assert entry.title == entry.title.strip()
        assert "<" not in entry.title
        assert entry.link.startswith(("http://", "https://"))
        assert entry.source == parser.source_name
        assert DATE_RE.match(entry.date_scraped)
        assert "<" not in entry.content, "content must have HTML stripped"
        assert len(entry.content) <= 501, "content is a snippet (500 chars + ellipsis)"


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.__name__)
def test_n_caps_the_number_of_entries(parser: type[PageParser]) -> None:
    collection = parser.parse_entries(load(FIXTURE_FOR[parser]), 2)

    assert collection is not None
    assert len(collection.entries) == 2


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.__name__)
def test_parser_declares_absolute_feed_urls(parser: type[PageParser]) -> None:
    assert parser.source_name
    assert parser.urls
    assert all(url.startswith("https://") for url in parser.urls)


def test_nation_news_strips_tracking_params_and_wordpress_footer() -> None:
    collection = NationNewsParser.parse_entries(load("nationnews.xml"), 50)

    assert collection is not None
    for entry in collection.entries:
        assert "utm_" not in entry.link
        assert entry.link.startswith("https://nationnews.com/")
        assert "appeared first on" not in entry.content
        assert entry.content, "Nation News items carry an excerpt"


def test_barbados_today_snippets_are_clean() -> None:
    collection = BarbadosTodayParser.parse_entries(load("barbadostoday.xml"), 50)

    assert collection is not None
    for entry in collection.entries:
        assert entry.link.startswith("https://barbadostoday.bb/")
        assert "appeared first on" not in entry.content
        assert entry.content


def test_bbc_strips_at_tracking_params() -> None:
    collection = BBCBarbadosParser.parse_entries(load("bbc.xml"), 50)

    assert collection is not None
    for entry in collection.entries:
        assert "at_medium" not in entry.link
        assert "at_campaign" not in entry.link
        assert "?" not in entry.link
        assert entry.content


def test_barbados_today_atom_variant_matches_rss() -> None:
    rss = BarbadosTodayParser.parse_entries(load("barbadostoday.xml"), 50)
    atom = BarbadosTodayParser.parse_entries(load("barbadostoday_atom.xml"), 50)

    assert rss is not None
    assert atom is not None
    assert len(atom.entries) >= 5
    assert {entry.link for entry in atom.entries} == {
        entry.link for entry in rss.entries
    }
    assert {entry.title for entry in atom.entries} == {
        entry.title for entry in rss.entries
    }


def test_advocate_fixture_is_escaped_drupal_rss() -> None:
    """The Advocate feed escapes its HTML instead of using CDATA; it must still strip clean."""
    collection = BarbadosAdvocateParser.parse_entries(load("advocate.xml"), 50)

    assert collection is not None
    first = collection.entries[0]
    assert first.title == "Summit to assist entrepreneurs on path to success"
    assert first.link == (
        "http://www.barbadosadvocate.com/business/summit-assist-entrepreneurs-path-success"
    )
    assert "field-item" not in first.content
    assert "&lt;" not in first.content


# --------------------------------------------------------------------------- edge cases


def test_empty_feed_returns_none() -> None:
    assert ExampleFeedParser.parse_entries(load("empty.xml"), 10) is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "<html><body><h1>Not a feed</h1></body></html>",
        "<rss><channel><item>",
        "﻿\x00",
    ],
    ids=["empty", "blank", "html", "truncated-xml", "garbage"],
)
def test_invalid_input_returns_none(text: str) -> None:
    assert ExampleFeedParser.parse_entries(text, 10) is None


def test_zero_n_returns_none() -> None:
    assert ExampleFeedParser.parse_entries(load("duplicate_links.xml"), 0) is None


def test_items_without_a_usable_link_or_title_are_skipped() -> None:
    collection = ExampleFeedParser.parse_entries(load("missing_link.xml"), 10)

    assert collection is not None
    assert [entry.link for entry in collection.entries] == [
        "https://example.test/stories/1",
        "https://example.test/stories/4",
    ]


def test_duplicate_links_are_collapsed_after_normalisation() -> None:
    collection = ExampleFeedParser.parse_entries(load("duplicate_links.xml"), 10)

    assert collection is not None
    assert [entry.link for entry in collection.entries] == [
        "https://example.test/stories/a",
        "https://example.test/stories/b?page=2",
    ]


def test_minimal_atom_feed() -> None:
    collection = ExampleFeedParser.parse_entries(load("atom_minimal.xml"), 10)

    assert collection is not None
    assert [entry.link for entry in collection.entries] == [
        "https://example.test/food/fish-and-chips",
        "https://example.test/news/relative-story",
    ]
    first, second = collection.entries
    assert first.title == "Fish & chips review"
    assert first.content == "Crispy & golden."
    assert second.content == "Structured xhtml content."
    assert all(entry.source == "Example Feed" for entry in collection.entries)


def test_xml_declaration_with_foreign_encoding_is_tolerated() -> None:
    text = load("duplicate_links.xml").replace(
        'encoding="UTF-8"', 'encoding="ISO-8859-1"'
    )

    collection = ExampleFeedParser.parse_entries(text, 10)

    assert collection is not None
    assert len(collection.entries) == 2


# --------------------------------------------------------------------------- helpers


def test_strip_html_removes_tags_and_unescapes_entities() -> None:
    assert (
        strip_html("<p>Tom &amp; Jerry&#8217;s <b>day</b> out</p>")
        == "Tom & Jerry’s day out"
    )


def test_strip_html_collapses_whitespace() -> None:
    assert strip_html("  line one \n\n\t line <br/> two  ") == "line one line two"


def test_strip_html_handles_empty_input() -> None:
    assert strip_html("") == ""
    assert strip_html("   ") == ""


def test_truncate_keeps_short_text() -> None:
    assert truncate("short text", 500) == "short text"


def test_truncate_cuts_on_a_word_boundary_with_ellipsis() -> None:
    text = "alpha beta gamma delta"

    assert truncate(text, 10) == "alpha beta…"
    assert truncate(text, 12) == "alpha beta…"
    assert truncate(text, 21) == "alpha beta gamma…"


def test_truncate_hard_cuts_when_there_is_no_boundary() -> None:
    assert truncate("x" * 30, 10) == "x" * 10 + "…"


def test_truncate_default_limit_is_about_500() -> None:
    result = truncate("word " * 200)

    assert result.endswith("…")
    assert 450 <= len(result) <= 501


# --------------------------------------------------------------------------- orchestration


def _fixture_for_url() -> dict[str, str]:
    return {
        url: load(FIXTURE_FOR[parser])
        for parser in scrape.PARSERS
        for url in parser.urls
    }


def test_registry_lists_live_parsers_and_keeps_dormant_ones_out() -> None:
    assert scrape.PARSERS
    assert all(issubclass(parser, PageParser) for parser in scrape.PARSERS)
    assert not set(scrape.PARSERS) & set(scrape.DORMANT_PARSERS)
    assert set(scrape.PARSERS) | set(scrape.DORMANT_PARSERS) == set(ALL_PARSERS)


@pytest.mark.asyncio
async def test_run_stores_one_collection_per_source_url() -> None:
    fixtures = _fixture_for_url()

    async def fake_fetch(url: str, timeout: float | None = None) -> str:
        return fixtures[url]

    fetch_text = AsyncMock(side_effect=fake_fetch)
    add_news_entries = AsyncMock()
    with (
        patch.object(Scraper, "fetch_text", new=fetch_text),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run()

    assert add_news_entries.await_count == len(fixtures)
    for call in add_news_entries.await_args_list:
        assert len(call.args) == 1
        assert not call.kwargs
        assert isinstance(call.args[0], NewsCollection)
        assert call.args[0].entries
    assert total == sum(
        len(call.args[0].entries) for call in add_news_entries.await_args_list
    )

    timeout_for_url = {
        url: parser.request_timeout for parser in scrape.PARSERS for url in parser.urls
    }
    assert fetch_text.await_count == len(fixtures)
    for call in fetch_text.await_args_list:
        assert call.kwargs["timeout"] == timeout_for_url[call.args[0]]


def test_nation_news_gets_a_longer_timeout_than_the_default() -> None:
    """Its origin takes 20-30 seconds to answer; the session default would time out."""
    assert NationNewsParser.request_timeout is not None
    assert NationNewsParser.request_timeout > 20
    assert BarbadosTodayParser.request_timeout is None
    assert BBCBarbadosParser.request_timeout is None


@pytest.mark.asyncio
async def test_one_failing_source_does_not_abort_the_others() -> None:
    fixtures = _fixture_for_url()
    failing_urls = set(NationNewsParser.urls)

    async def fake_fetch(url: str, timeout: float | None = None) -> str:
        if url in failing_urls:
            raise aiohttp.ClientConnectionError("simulated outage")
        return fixtures[url]

    add_news_entries = AsyncMock()
    with (
        patch.object(Scraper, "fetch_text", new=AsyncMock(side_effect=fake_fetch)),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run()

    assert add_news_entries.await_count == len(fixtures) - len(failing_urls)
    stored_sources = {
        call.args[0].entries[0].source for call in add_news_entries.await_args_list
    }
    assert NationNewsParser.source_name not in stored_sources
    assert {
        BarbadosTodayParser.source_name,
        BBCBarbadosParser.source_name,
    } <= stored_sources
    assert total > 0


@pytest.mark.asyncio
async def test_db_failure_for_one_source_is_isolated() -> None:
    fixtures = _fixture_for_url()

    async def fake_fetch(url: str, timeout: float | None = None) -> str:
        return fixtures[url]

    async def flaky_add(collection: NewsCollection) -> None:
        if collection.entries[0].source == BBCBarbadosParser.source_name:
            raise RuntimeError("simulated database error")

    add_news_entries = AsyncMock(side_effect=flaky_add)
    with (
        patch.object(Scraper, "fetch_text", new=AsyncMock(side_effect=fake_fetch)),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run()

    assert add_news_entries.await_count == len(fixtures)
    assert total > 0


@pytest.mark.asyncio
async def test_run_with_parser_whose_fetch_returns_nothing_parsable() -> None:
    add_news_entries = AsyncMock()
    with (
        patch.object(
            Scraper, "fetch_text", new=AsyncMock(return_value="<html>down</html>")
        ),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run()

    assert total == 0
    add_news_entries.assert_not_awaited()
