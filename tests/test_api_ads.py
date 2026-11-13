from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.service import OlxService, get_olx_service
from database import save_ad, save_price
from tests.helpers import make_ad

DETAILS = {"description": "Нова, у плівці", "photos": ["https://img/1.jpg", "https://img/2.jpg"],
           "price": {"price": 500, "currency": "USD", "converted": False, "label": None}}


@pytest.fixture
def client():
    service = OlxService()
    app.dependency_overrides[get_olx_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_details_come_from_scraper_by_saved_link(client):
    save_ad(make_ad(), "сумка")
    with patch("api.main.scrape_details", return_value=DETAILS) as scrape:
        response = client.get("/ads/olx/909426485")
    assert response.status_code == 200
    assert response.json() == DETAILS
    scrape.assert_called_once_with(make_ad()["link"])


def test_details_of_unknown_ad_is_404_without_scraping(client):
    with patch("api.main.scrape_details") as scrape:
        response = client.get("/ads/olx/unknown")
    assert response.status_code == 404
    scrape.assert_not_called()


def test_details_with_empty_scrape_result_has_null_price(client):
    save_ad(make_ad(), "сумка")
    empty = {"description": None, "photos": [], "price": None}
    with patch("api.main.scrape_details", return_value=empty):
        assert client.get("/ads/olx/909426485").json() == empty


def test_unknown_source_is_422(client):
    assert client.get("/ads/ebay/1").status_code == 422
    assert client.get("/ads/ebay/1/price-history").status_code == 422


def test_price_history_in_order_with_currency(client):
    save_ad(make_ad(), "сумка")
    save_price("909426485", "olx", 2500, "UAH")
    save_price("909426485", "olx", 2200, "UAH")
    body = client.get("/ads/olx/909426485/price-history").json()
    assert body["source"] == "olx"
    assert body["ad_id"] == "909426485"
    assert [(point["price"], point["currency"]) for point in body["points"]] == [(2500, "UAH"), (2200, "UAH")]
    assert body["points"][0]["changed_at"]


def test_price_history_of_ad_without_records_is_empty_list(client):
    save_ad(make_ad(), "сумка")
    assert client.get("/ads/olx/909426485/price-history").json()["points"] == []


def test_price_history_of_unknown_ad_is_404(client):
    assert client.get("/ads/olx/unknown/price-history").status_code == 404
