from unittest.mock import MagicMock, patch

import pytest

from scrapers import olx


def card(ad_id, town="Київ"):
    return (f'<div data-cy="l-card" id="{ad_id}">'
            f'<a data-testid="card-title-link" href="/d/obyavlenie/{ad_id}.html">Товар {ad_id}</a>'
            f'<p data-testid="ad-price">100 грн.</p>'
            f'<p data-testid="location-date">{town} - Сьогодні о 10:00</p></div>')


def page(*grids):
    body = "".join(f'<div data-testid="listing-grid">{"".join(cards)}</div>' for cards in grids)
    return f"<html><body>{body}</body></html>"


@pytest.fixture
def olx_get():
    response = MagicMock(status_code=200, content=page([]).encode("utf-8"))
    with patch.object(olx.requests, "get", return_value=response) as get:
        yield get


def serve(olx_get, html):
    olx_get.return_value.content = html.encode("utf-8")


def test_ignores_cards_from_other_locations_grid(olx_get):
    serve(olx_get, page([card("a"), card("b")], [card("other", "Дніпро")]))
    assert [ad["id"] for ad in olx.scrape("iphone")] == ["a", "b"]


def test_no_results_ignores_suggested_ads(olx_get):
    serve(olx_get, page([], [card("ad1", "Дніпро"), card("ad2", "Харків")]))
    assert olx.scrape("zzqxjwvkpl") == []


def test_default_search_url_without_city_and_state(olx_get):
    olx.scrape("iphone", 2)
    url = olx_get.call_args.args[0]
    params = olx_get.call_args.kwargs["params"]
    assert url == "https://www.olx.ua/uk/list/q-iphone/"
    assert params["page"] == 2
    assert "search[filter_enum_state][0]" not in params


def test_city_goes_to_path_and_state_to_params(olx_get):
    olx.scrape("iphone", city="lviv", state="used", max_price=5000)
    url = olx_get.call_args.args[0]
    params = olx_get.call_args.kwargs["params"]
    assert url == "https://www.olx.ua/uk/lvov/q-iphone/"
    assert params["search[filter_enum_state][0]"] == "used"
    assert params["search[filter_float_price:to]"] == 5000


def test_timeout_raises_olx_error(olx_get):
    olx_get.side_effect = olx.requests.exceptions.Timeout("curl: (28) Operation timed out")
    with pytest.raises(olx.OlxError, match="таймаут"):
        olx.scrape("iphone")


def test_network_failure_raises_olx_error(olx_get):
    olx_get.side_effect = ConnectionError("reset")
    with pytest.raises(olx.OlxError, match="мережа"):
        olx.scrape("iphone")


def test_bad_status_raises_olx_error(olx_get):
    olx_get.return_value.status_code = 429
    with pytest.raises(olx.OlxError, match="HTTP 429"):
        olx.scrape("iphone")
