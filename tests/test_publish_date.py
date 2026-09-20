"""Articles carry the time their publisher posted them, and the card shows it.

The feed is ordered by that time (see ``test_queries``); when a feed gives no
date the entry keeps ``published_at = None`` and falls back to insertion time
at query time, so no article is ever shown with an invented publish date.
"""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.models import NewsCollection, NewsEntry
from app.services.page_parser import BarbadosTodayParser

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_model_defaults_published_at_to_none() -> None:
    entry = NewsEntry(
        title="T", content="", source="S", link="https://x/1", date_scraped="2026-09-20"
    )

    assert entry.published_at is None


def test_rss_items_carry_their_pubdate() -> None:
    text = fixture("barbadostoday.xml")
    collection = BarbadosTodayParser.parse_entries(text, 50)
    assert collection is not None

    first_raw = re.search(r"<pubDate>([^<]+)</pubDate>", text)
    assert first_raw is not None
    assert all(entry.published_at is not None for entry in collection.entries)
    first = collection.entries[0].published_at
    assert first is not None
    assert first == parsedate_to_datetime(first_raw[1])
    assert first.tzinfo is not None


def test_atom_entries_carry_published_or_updated() -> None:
    collection = BarbadosTodayParser.parse_entries(
        fixture("barbadostoday_atom.xml"), 50
    )
    assert collection is not None

    assert all(entry.published_at is not None for entry in collection.entries)


def test_items_without_a_date_have_no_published_at() -> None:
    collection = BarbadosTodayParser.parse_entries(fixture("duplicate_links.xml"), 50)
    assert collection is not None

    assert all(entry.published_at is None for entry in collection.entries)


def test_build_entry_parses_feed_dates_and_tolerates_garbage() -> None:
    def make(raw: str | None) -> NewsEntry:
        entry = BarbadosTodayParser.build_entry(
            title="T",
            link="https://x/y",
            content="",
            base_url="https://x",
            published=raw,
        )
        assert entry is not None
        return entry

    expected = datetime(2026, 9, 20, 10, tzinfo=UTC)
    assert make("Sat, 20 Sep 2026 10:00:00 +0000").published_at == expected
    assert make("2026-09-20T10:00:00Z").published_at == expected
    # A timestamp without a zone is taken as UTC rather than left naive.
    assert make("Sat, 20 Sep 2026 10:00:00").published_at == expected
    assert make("not a date").published_at is None
    assert make(None).published_at is None


def test_card_shows_the_publish_date_when_known_else_the_scrape_date(client, mock_db):
    dated = NewsEntry(
        title="Dated",
        content="Body",
        source="S",
        link="https://x/1",
        date_scraped="2026-09-20",
        published_at=datetime(2026, 9, 18, 12, tzinfo=UTC),
    )
    undated = NewsEntry(
        title="Undated",
        content="Body",
        source="S",
        link="https://x/2",
        date_scraped="2026-09-20",
    )
    mock_db.get_entries.return_value = NewsCollection(entries=[dated, undated])

    html = client.get("/htmx/entries").text

    times = re.findall(r"<time[^>]*>\s*([^<\s]+)\s*</time>", html)
    assert times == ["2026-09-18", "2026-09-20"]


def test_card_omits_the_description_block_when_content_is_empty(client, mock_db):
    empty = NewsEntry(
        title="No snippet",
        content="",
        source="S",
        link="https://x/3",
        date_scraped="2026-09-20",
    )
    full = NewsEntry(
        title="Snippet",
        content="Some text",
        source="S",
        link="https://x/4",
        date_scraped="2026-09-20",
    )
    mock_db.get_entries.return_value = NewsCollection(entries=[empty, full])

    html = client.get("/htmx/entries").text

    assert html.count('class="prose') == 1
    assert "Some text" in html
