"""Smoke tests: the page and the HTMX partials respond with the expected content.

Assertions are deliberately behaviour-only (status code plus presence of text)
so they survive refactors of the rendering path.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.models import NewsEntry, Summary


def test_index_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Bajan Insider" in response.text


def test_htmx_entries_lists_mocked_entry(
    client: TestClient, mock_db: SimpleNamespace, sample_entry: NewsEntry
) -> None:
    response = client.get("/htmx/entries")

    assert response.status_code == 200
    assert sample_entry.title in response.text


def test_htmx_summary_returns_cached_summary(
    client: TestClient, mock_db: SimpleNamespace
) -> None:
    mock_db.get_summary.return_value = Summary(
        title_hash="x", ai_summary="Cached summary text"
    )

    response = client.get("/htmx/summary")

    assert response.status_code == 200
    assert "Cached summary text" in response.text


def test_htmx_summary_renders_bullets_as_list(
    client: TestClient, mock_db: SimpleNamespace
) -> None:
    mock_db.get_summary.return_value = Summary(
        title_hash="x", ai_summary="Intro.\n- <b>One</b>\n- Two"
    )

    response = client.get("/htmx/summary")

    assert response.status_code == 200
    assert "<p" in response.text and "Intro." in response.text
    assert response.text.count("<li") == 2
    # Model output is still escaped, never rendered as markup.
    assert "&lt;b&gt;One&lt;/b&gt;" in response.text
