import asyncio
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import service as service_module
from api.cache import TTLCache
from api.main import app
from api.service import OlxService, get_olx_service
from scrapers.olx import OlxError
from tests.helpers import make_ad, named_ad


@pytest.fixture
def olx():
    service = OlxService()
    app.dependency_overrides[get_olx_service] = lambda: service
    with patch.object(service_module, "search") as search, patch.object(service_module, "search_recent") as recent:
        search.return_value = [make_ad()]
        recent.return_value = [make_ad()]
        service.search = search
        service.search_recent = recent
        yield service
    app.dependency_overrides.clear()


@pytest.fixture
def client(olx):
    return TestClient(app)


def test_search_returns_ads_described_by_model(client, olx):
    response = client.get("/search", params={"q": "сумка"})
    body = response.json()
    assert response.status_code == 200
    assert body["count"] == 1
    assert body["cached"] is False
    assert body["ads"][0]["id"] == "909426485"
    assert body["ads"][0]["currency"] == "UAH"


def test_filters_are_passed_to_scraper(client, olx):
    client.get("/search", params={"q": "iphone", "min_price": 100, "max_price": 900, "sort": "cheap",
                                  "city": "lviv", "state": "used", "page": 3})
    olx.search.assert_called_once_with("iphone", 3, min_price=100, max_price=900, sort="cheap",
                                       city="lviv", state="used")


def test_period_uses_recent_search_and_ignores_page(client, olx):
    client.get("/search", params={"q": "iphone", "period": "3d", "page": 5})
    olx.search_recent.assert_called_once_with("iphone", "3d", min_price=None, max_price=None, sort="new",
                                              city=None, state=None)
    olx.search.assert_not_called()


def test_price_filter_is_applied_after_olx(client, olx):
    olx.search.return_value = [named_ad("a", "Лампа"), make_ad(price=None, ad_id="b"), make_ad(price=5000, ad_id="c")]
    body = client.get("/search", params={"q": "лампа", "max_price": 3000}).json()
    assert [ad["id"] for ad in body["ads"]] == ["a"]


def test_exact_keeps_only_titles_with_all_words(client, olx):
    olx.search.return_value = [named_ad("a", "iPhone 13 Pro"), named_ad("b", "iPhone 12")]
    body = client.get("/search", params={"q": "iphone 13", "exact": "true"}).json()
    assert [ad["id"] for ad in body["ads"]] == ["a"]


def test_promoted_ads_go_last(client, olx):
    promoted = {**make_ad(ad_id="p"), "promoted": True}
    olx.search.return_value = [promoted, make_ad(ad_id="n")]
    body = client.get("/search", params={"q": "сумка"}).json()
    assert [ad["id"] for ad in body["ads"]] == ["n", "p"]


def test_olx_error_becomes_502(client, olx):
    olx.search.side_effect = OlxError("таймаут")
    response = client.get("/search", params={"q": "сумка"})
    assert response.status_code == 502
    assert response.json() == {"detail": "OLX не відповів: таймаут"}


@pytest.mark.parametrize("params", [
    {},
    {"q": ""},
    {"q": "a", "sort": "random"},
    {"q": "a", "city": "atlantis"},
    {"q": "a", "state": "broken"},
    {"q": "a", "period": "30d"},
    {"q": "a", "min_price": 0},
    {"q": "a", "page": 0},
    {"q": "a", "min_price": 500, "max_price": 100},
])
def test_bad_parameters_are_422(client, olx, params):
    assert client.get("/search", params=params).status_code == 422
    olx.search.assert_not_called()


def test_second_identical_search_comes_from_cache(client, olx):
    first = client.get("/search", params={"q": "Сумка"}).json()
    second = client.get("/search", params={"q": " сумка "}).json()
    assert (first["cached"], second["cached"]) == (False, True)
    assert olx.search.call_count == 1


def test_different_filters_are_not_cache_hits(client, olx):
    client.get("/search", params={"q": "сумка"})
    client.get("/search", params={"q": "сумка", "city": "kyiv"})
    client.get("/search", params={"q": "сумка", "page": 2})
    assert olx.search.call_count == 3


def test_olx_error_is_not_cached(client, olx):
    olx.search.side_effect = [OlxError("таймаут"), [make_ad()]]
    assert client.get("/search", params={"q": "сумка"}).status_code == 502
    assert client.get("/search", params={"q": "сумка"}).status_code == 200


def test_cache_returns_copies(client, olx):
    client.get("/search", params={"q": "сумка"})
    olx.search_cache.items[next(iter(olx.search_cache.items))][1][0]["name"] = "stored"
    stored = client.get("/search", params={"q": "сумка"}).json()["ads"][0]
    assert stored["name"] == "stored"


def test_cache_entry_expires():
    now = [0]
    cache = TTLCache(ttl_seconds=10, max_size=2, clock=lambda: now[0])
    cache.set("a", 1)
    now[0] = 9
    assert cache.get("a") == 1
    now[0] = 10
    assert cache.get("a") is None


def test_cache_drops_oldest_when_full():
    cache = TTLCache(ttl_seconds=10, max_size=2)
    for key in "abc":
        cache.set(key, key)
    assert [cache.get(key) for key in "abc"] == [None, "b", "c"]


async def test_no_more_than_two_olx_requests_at_once():
    service = OlxService(max_parallel=2)
    running = 0
    peak = 0
    guard = threading.Lock()

    def slow_search(*args, **kwargs):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with guard:
            running -= 1
        return []

    with patch.object(service_module, "search", slow_search):
        await asyncio.gather(*[
            service.find_ads(f"q{number}", None, None, "new", "any", None, None, 1) for number in range(6)])
    assert peak == 2


async def test_slow_scraper_does_not_block_event_loop():
    service = OlxService()
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    with patch.object(service_module, "search", lambda *args, **kwargs: time.sleep(0.2) or []):
        await service.find_ads("q", None, None, "new", "any", None, None, 1)
    task.cancel()
    assert ticks >= 5
