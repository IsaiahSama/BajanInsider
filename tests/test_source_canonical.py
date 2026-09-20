"""Publisher labels are canonicalised so one outlet has exactly one name stored.

The database's secondary identity is ``(title, source)``; if the same outlet is
labelled "BBC" by an aggregator and "BBC News" by its own feed, the same story
is stored twice. Canonicalising at parse time closes that gap.
"""

import pytest

from app.services.page_parser import BBCBarbadosParser, canonical_source


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BBC", "BBC News"),
        ("bbc", "BBC News"),
        ("BBC News", "BBC News"),
        ("Unesco", "UNESCO"),
        ("news - Mongabay", "Mongabay"),
        ("nationnews.com", "Nation News"),
        ("barbadostoday.bb", "Barbados Today"),
        # Unknown labels are only whitespace-normalised, never invented.
        ("  The   Guardian ", "The Guardian"),
        ("Devon Live", "Devon Live"),
    ],
)
def test_canonical_source(raw: str, expected: str) -> None:
    assert canonical_source(raw) == expected


def test_build_entry_stores_the_canonical_source() -> None:
    entry = BBCBarbadosParser.build_entry(
        title="Sugar arrangement in limbo",
        link="https://www.bbc.co.uk/news/articles/abc",
        content="",
        base_url="https://www.bbc.co.uk",
        source="BBC",
    )

    assert entry is not None
    assert entry.source == "BBC News"


def test_build_entry_canonicalises_the_parser_default_too() -> None:
    class SloppyParser(BBCBarbadosParser):
        source_name = "bbc"

    entry = SloppyParser.build_entry(
        title="T",
        link="https://www.bbc.co.uk/x",
        content="",
        base_url="https://bbc.co.uk",
    )

    assert entry is not None
    assert entry.source == "BBC News"
