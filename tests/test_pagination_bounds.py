"""A non-positive page number must render page 1, not 500 on a negative skip()."""

import pytest


@pytest.mark.parametrize("page", [0, -5])
def test_non_positive_page_renders_first_page(client, mock_db, page):
    response = client.get(f"/htmx/entries?page={page}")

    assert response.status_code == 200
    mock_db.get_entries.assert_awaited_once_with(0, 30)


@pytest.mark.parametrize("page", [0, -5])
def test_non_positive_page_on_search_renders_first_page(client, mock_db, page):
    response = client.post(
        f"/htmx/entries/filter?page={page}", data={"search": "bridgetown"}
    )

    assert response.status_code == 200
    mock_db.find_entry.assert_awaited_once_with("bridgetown")
