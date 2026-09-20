"""Tests for the Google News RSS aggregator parser and the per-source entry cap it needs.

``tests/fixtures/googlenews.xml`` is a live capture (100 items) of the Google News search
feed for "barbados news" in the ``en-GB`` edition. Its items are unusual: ``<title>`` ends
with `` - <Publisher>``, ``<link>`` is a ``news.google.com/rss/articles/…`` redirect,
``<description>`` is just an anchor plus the publisher name, and a ``<source>`` element
names the publisher. The hand-written feeds below exercise the edge cases the capture does
not. Nothing here touches the network or the database.
"""

import html
import re
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, patch

from app.models.news_collection import NewsCollection
from app.services import scrape
from app.services.page_parser import (
    BarbadosTodayParser,
    BBCBarbadosParser,
    GoogleNewsRSSParser,
    NationNewsParser,
    PageParser,
    RSSParser,
)
from app.services.scraper import Scraper

FIXTURES = Path(__file__).parent / "fixtures"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GOOGLE_ARTICLE_PREFIX = "https://news.google.com/rss/articles/"


def load(name: str) -> str:
    """Read a fixture file as text."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse(text: str, n: int = 50) -> NewsCollection:
    """Parse ``text`` with the Google parser, asserting something came out."""
    collection = GoogleNewsRSSParser.parse_entries(text, n)
    assert collection is not None
    return collection


def google_feed(items: str) -> str:
    """Wrap hand-written ``<item>`` markup in the envelope Google emits."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>'
        '<generator>NFE/5.0</generator><title>"barbados news" - Google News</title>'
        "<link>https://news.google.com/search?q=barbados+news</link>"
        f"{items}</channel></rss>"
    )


def google_item(
    title: str, *, source: str | None, key: str, with_link: bool = True
) -> str:
    """One ``<item>`` shaped like Google's: redirect link, non-permalink guid, anchor body."""
    url = f"{GOOGLE_ARTICLE_PREFIX}{key}?oc=5"
    escaped_title = html.escape(title, quote=False)
    parts = [f"<title>{escaped_title}</title>"]
    if with_link:
        parts.append(f"<link>{url}</link>")
    parts.append(f'<guid isPermaLink="false">{key}</guid>')
    parts.append("<pubDate>Sun, 20 Sep 2026 15:08:22 GMT</pubDate>")
    parts.append(
        f'<description>&lt;a href="{url}" target="_blank"&gt;{escaped_title}&lt;/a&gt;'
        "&amp;nbsp;&amp;nbsp;&lt;font color=&quot;#6f6f6f&quot;&gt;Publisher&lt;/font&gt;"
        "</description>"
    )
    if source is not None:
        parts.append(f'<source url="https://example.test">{source}</source>')
    return f"<item>{''.join(parts)}</item>"


def synthetic_google_feed(count: int) -> str:
    """A Google-shaped feed with ``count`` distinct items, for cap tests."""
    return google_feed(
        "".join(
            google_item(
                f"Story {i} - Publisher {i}", source=f"Publisher {i}", key=f"K{i}"
            )
            for i in range(count)
        )
    )


def plain_feed(parser: type[PageParser], count: int) -> str:
    """An ordinary RSS 2.0 feed with ``count`` items, for a first-party parser."""
    items = "".join(
        f"<item><title>Story {i}</title>"
        f"<link>https://example.test/{parser.__name__}/{i}</link>"
        f"<description>Snippet {i}</description></item>"
        for i in range(count)
    )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>'
        f"<link>https://example.test/</link>{items}</channel></rss>"
    )


# --------------------------------------------------------------------------- live capture


def test_fixture_parses_to_valid_entries() -> None:
    collection = parse(load("googlenews.xml"), 200)

    assert isinstance(collection, NewsCollection)
    assert len(collection.entries) >= 20

    links = [entry.link for entry in collection.entries]
    assert len(links) == len(set(links)), "links must be unique within a parse"

    for entry in collection.entries:
        assert entry.title.strip(), "title must not be blank"
        assert entry.title == entry.title.strip()
        assert "<" not in entry.title
        assert entry.link.startswith("https://")
        assert entry.content == "", "Google's description is not a snippet"
        assert DATE_RE.match(entry.date_scraped)
        # Every captured item carries <source>, so the fallback label never appears.
        assert entry.source
        assert entry.source != GoogleNewsRSSParser.source_name
        assert not entry.title.lower().endswith(f" - {entry.source.lower()}")


def test_fixture_publishers_become_the_source() -> None:
    sources = {entry.source for entry in parse(load("googlenews.xml"), 200).entries}

    assert {"Barbados Today", "BBC News", "The Guardian", "Devon Live"} <= sources


def test_fixture_titles_lose_only_the_publisher_suffix() -> None:
    source_by_title = {
        entry.title: entry.source
        for entry in parse(load("googlenews.xml"), 200).entries
    }

    assert source_by_title["Captains positive ahead of CPL Final"] == "Barbados Today"
    # An inner " - " that is not the publisher survives.
    assert (
        source_by_title["Barbados fatal crash court ruling 'extraordinary' - coroner"]
        == "BBC News"  # "BBC" from the feed, canonicalised to the label our own parser uses
    )
    # A publisher whose own name contains " - " is removed whole.
    assert (
        source_by_title["Fly direct to Barbados this winter"] == "Travel Weekly - Home"
    )


def test_fixture_links_keep_googles_redirect_url() -> None:
    for entry in parse(load("googlenews.xml"), 200).entries:
        assert entry.link.startswith(GOOGLE_ARTICLE_PREFIX)
        assert entry.link.endswith("?oc=5")


def test_n_caps_the_number_of_entries() -> None:
    assert len(parse(load("googlenews.xml"), 5).entries) == 5


def test_overlapping_stories_match_the_first_party_feed_on_title_and_source() -> None:
    """The unique index is on ``(title, source, date_scraped)``.

    A story Google surfaces from an outlet that is already a first-party source must come
    out with the same title and source as that outlet's own feed, so the index drops the
    second copy. Both fixtures were captured the same day and share several stories.
    """
    google = parse(load("googlenews.xml"), 200)
    barbados_today = BarbadosTodayParser.parse_entries(load("barbadostoday.xml"), 200)
    assert barbados_today is not None

    shared = {(entry.title, entry.source) for entry in google.entries} & {
        (entry.title, entry.source) for entry in barbados_today.entries
    }
    assert ("Captains positive ahead of CPL Final", "Barbados Today") in shared
    assert len(shared) >= 3


# --------------------------------------------------------------------------- edge cases


def test_item_without_source_falls_back_to_the_title_suffix() -> None:
    feed = google_feed(
        google_item("Sugar arrangement in limbo - Barbados Today", source=None, key="A")
    )

    (entry,) = parse(feed).entries
    assert entry.title == "Sugar arrangement in limbo"
    assert entry.source == "Barbados Today"


def test_item_without_source_or_suffix_falls_back_to_google_news() -> None:
    feed = google_feed(google_item("Sugar arrangement in limbo", source=None, key="A"))

    (entry,) = parse(feed).entries
    assert entry.title == "Sugar arrangement in limbo"
    assert entry.source == "Google News"


def test_title_segment_that_is_not_the_source_is_kept() -> None:
    feed = google_feed(
        google_item("Clash of the titans - part two", source="Nation News", key="A")
    )

    (entry,) = parse(feed).entries
    assert entry.title == "Clash of the titans - part two"
    assert entry.source == "Nation News"


def test_only_the_last_segment_is_stripped() -> None:
    feed = google_feed(
        google_item(
            "Budget 2026 - what it means for you - Barbados Today",
            source="Barbados Today",
            key="A",
        )
    )

    (entry,) = parse(feed).entries
    assert entry.title == "Budget 2026 - what it means for you"


def test_publisher_name_containing_a_dash_is_removed_whole() -> None:
    publisher = "ABC News - Breaking News, Latest News and Videos"
    feed = google_feed(
        google_item(
            f"Prince Harry meets Rihanna in Barbados - {publisher}",
            source=publisher,
            key="A",
        )
    )

    (entry,) = parse(feed).entries
    assert entry.title == "Prince Harry meets Rihanna in Barbados"
    assert entry.source == publisher


def test_suffix_match_ignores_case_and_whitespace() -> None:
    feed = google_feed(
        google_item(
            "Sugar arrangement in limbo -  barbados   TODAY",
            source=" Barbados  Today ",
            key="A",
        )
    )

    (entry,) = parse(feed).entries
    assert entry.title == "Sugar arrangement in limbo"
    assert entry.source == "Barbados Today"


def test_content_is_empty_even_though_the_description_has_text() -> None:
    feed = google_feed(
        google_item("Sugar arrangement in limbo - BBC", source="BBC", key="A")
    )

    (entry,) = parse(feed).entries
    assert entry.content == ""


def test_item_without_a_link_is_skipped() -> None:
    feed = google_feed(
        google_item("Kept - Barbados Today", source="Barbados Today", key="A")
        + google_item("Dropped - BBC", source="BBC", key="B", with_link=False)
        + google_item("Also kept - BBC", source="BBC", key="C")
    )

    assert [entry.title for entry in parse(feed).entries] == ["Kept", "Also kept"]


def test_empty_or_invalid_feed_returns_none() -> None:
    assert GoogleNewsRSSParser.parse_entries(google_feed(""), 10) is None
    assert GoogleNewsRSSParser.parse_entries("<html>blocked</html>", 10) is None


# --------------------------------------------------------------------------- registry & cap


def test_registered_live_and_last() -> None:
    assert GoogleNewsRSSParser in scrape.PARSERS
    assert scrape.PARSERS[-1] is GoogleNewsRSSParser
    assert GoogleNewsRSSParser not in scrape.DORMANT_PARSERS


def test_feed_url_is_the_rss_search_surface() -> None:
    (url,) = GoogleNewsRSSParser.urls

    assert url.startswith("https://news.google.com/rss/search?")
    assert "q=barbados+news" in url
    assert "ceid=GB:en" in url
    assert "when" not in url, "the recency knob is documented, not enabled"
    assert GoogleNewsRSSParser.request_timeout is None


def test_entries_per_url_cap_is_declared_only_by_google() -> None:
    assert PageParser.entries_per_url is None
    assert GoogleNewsRSSParser.entries_per_url == 40
    for parser in (NationNewsParser, BarbadosTodayParser, BBCBarbadosParser):
        assert parser.entries_per_url is None


async def test_run_keeps_40_google_entries_and_the_default_from_everyone_else() -> None:
    feeds = {
        url: plain_feed(parser, 60)
        for parser in scrape.PARSERS
        if parser is not GoogleNewsRSSParser
        for url in parser.urls
    }
    feeds.update({url: synthetic_google_feed(60) for url in GoogleNewsRSSParser.urls})

    async def fake_fetch(url: str, timeout: float | None = None) -> str:
        return feeds[url]

    add_news_entries = AsyncMock()
    with (
        patch.object(Scraper, "fetch_text", new=AsyncMock(side_effect=fake_fetch)),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run()

    stored: list[NewsCollection] = [
        call.args[0] for call in add_news_entries.await_args_list
    ]
    assert len(stored) == len(feeds)
    google = [c for c in stored if c.entries[0].link.startswith(GOOGLE_ARTICLE_PREFIX)]
    others = [
        c for c in stored if not c.entries[0].link.startswith(GOOGLE_ARTICLE_PREFIX)
    ]
    assert len(google) == 1
    assert len(google[0].entries) == 40
    assert others
    assert all(len(c.entries) == scrape.ENTRIES_PER_URL for c in others)
    assert total == 40 + scrape.ENTRIES_PER_URL * len(others)


async def test_parser_cap_beats_an_explicit_amount() -> None:
    class UncappedParser(RSSParser):
        source_name: ClassVar[str] = "Uncapped"
        urls: ClassVar[list[str]] = ["https://example.test/uncapped/feed/"]

    feeds = {
        UncappedParser.urls[0]: plain_feed(UncappedParser, 60),
        GoogleNewsRSSParser.urls[0]: synthetic_google_feed(60),
    }

    async def fake_fetch(url: str, timeout: float | None = None) -> str:
        return feeds[url]

    add_news_entries = AsyncMock()
    with (
        patch.object(Scraper, "fetch_text", new=AsyncMock(side_effect=fake_fetch)),
        patch.object(scrape.client, "add_news_entries", new=add_news_entries),
    ):
        total = await scrape.run(
            parsers=[UncappedParser, GoogleNewsRSSParser], amount=3
        )

    sizes = {
        call.args[0].entries[0].source == "Uncapped": len(call.args[0].entries)
        for call in add_news_entries.await_args_list
    }
    assert sizes == {True: 3, False: 40}
    assert total == 43
