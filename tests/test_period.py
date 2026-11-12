from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import core
from core import search_recent
from scrapers.olx import OlxError

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)


def ad(ad_id, published_date, price=100, promoted=False):
    return {"source": "olx", "id": ad_id, "published_date": published_date, "price": price, "promoted": promoted}


def pages_asked(search):
    return [call.args[1] for call in search.call_args_list]


@pytest.fixture
def recent():
    def run(pages, period, now=NOW, **kwargs):
        def fake_search(query, page, **filters):
            if pages.get(page) == "error":
                raise OlxError("таймаут")
            return [dict(item) for item in pages.get(page, [])]

        with patch.object(core, "search", side_effect=fake_search) as search:
            result = search_recent("диван", period, now=now, **kwargs)
        return [item["id"] for item in result], search

    return run


def test_three_days_includes_boundary_and_stops_on_old(recent):
    pages = {
        1: [ad("a", "Сьогодні о 10:00"), ad("b", "Вчора о 10:00"),
            ad("c", "09 жовтня 2026 р."), ad("d", "08 жовтня 2026 р.")],
        2: [ad("e", "Сьогодні о 09:00")],
    }
    ids, search = recent(pages, "3d")
    assert ids == ["a", "b", "c"]
    assert pages_asked(search) == [1]


def test_one_day_only_today(recent):
    ids, _ = recent({1: [ad("a", "Сьогодні о 10:00"), ad("b", "Вчора о 23:00")]}, "1d")
    assert ids == ["a"]


def test_old_promoted_ad_does_not_stop_paging(recent):
    pages = {
        1: [ad("top", "01 жовтня 2026 р.", promoted=True), ad("a", "Сьогодні о 10:00")],
        2: [ad("b", "Сьогодні о 08:00"), ad("old", "01 жовтня 2026 р.")],
        3: [ad("c", "Сьогодні о 07:00")],
    }
    ids, search = recent(pages, "1d")
    assert ids == ["a", "b"]
    assert pages_asked(search) == [1, 2]


def test_repeated_page_stops_without_duplicates(recent):
    page = [ad("a", "Сьогодні о 10:00"), ad("b", "Сьогодні о 09:00")]
    ids, search = recent({1: page, 2: page, 3: page}, "7d")
    assert ids == ["a", "b"]
    assert pages_asked(search) == [1, 2]


def test_stops_after_max_pages(recent):
    pages = {n: [ad(f"p{n}", "Сьогодні о 10:00")] for n in range(1, 10)}
    ids, search = recent(pages, "7d")
    assert search.call_count == core.MAX_PERIOD_PAGES
    assert len(ids) == core.MAX_PERIOD_PAGES


def test_unparsed_date_is_skipped_without_stopping(recent):
    pages = {1: [ad("a", "Сьогодні о 10:00"), ad("weird", "щось незрозуміле")], 2: [ad("b", "Сьогодні о 09:00")]}
    ids, search = recent(pages, "1d")
    assert ids == ["a", "b"]
    assert pages_asked(search) == [1, 2, 3]


def test_only_unparsed_dates_stop_at_max_pages(recent):
    pages = {n: [ad(f"w{n}", "щось незрозуміле")] for n in range(1, 10)}
    ids, search = recent(pages, "7d")
    assert ids == []
    assert search.call_count == core.MAX_PERIOD_PAGES


def test_today_follows_kyiv_calendar_after_midnight(recent):
    late = datetime(2026, 10, 11, 22, 30, tzinfo=timezone.utc)
    ids, _ = recent({1: [ad("a", "Сьогодні о 00:30"), ad("b", "Вчора о 23:50")]}, "1d", now=late)
    assert ids == ["a"]


def test_always_asks_olx_for_newest_and_passes_prices(recent):
    _, search = recent({1: [ad("a", "Сьогодні о 10:00")]}, "1d", min_price=100, max_price=500, sort="cheap")
    first_call = search.call_args_list[0].kwargs
    assert first_call["sort"] == "new"
    assert (first_call["min_price"], first_call["max_price"]) == (100, 500)


def test_error_on_later_page_keeps_found_ads(recent):
    pages = {1: [ad("a", "Сьогодні о 10:00")], 2: "error", 3: [ad("c", "Сьогодні о 08:00")]}
    ids, search = recent(pages, "1d")
    assert ids == ["a"]
    assert pages_asked(search) == [1, 2]


def test_error_on_first_page_is_raised(recent):
    with pytest.raises(OlxError):
        recent({1: "error"}, "1d")


def test_city_and_state_passed_to_every_page(recent):
    pages = {1: [ad("a", "Сьогодні о 10:00")], 2: [ad("b", "Сьогодні о 09:00")]}
    _, search = recent(pages, "1d", city="odesa", state="new")
    assert search.call_count == 3
    assert all(call.kwargs["city"] == "odesa" and call.kwargs["state"] == "new"
               for call in search.call_args_list)


def test_sort_new_puts_latest_day_first(recent):
    pages = {1: [ad("old", "10 жовтня 2026 р."), ad("new", "Сьогодні о 10:00")]}
    ids, _ = recent(pages, "3d")
    assert ids == ["new", "old"]


@pytest.mark.parametrize("sort, order", [("cheap", ["y", "x", "free"]), ("expensive", ["x", "y", "free"])])
def test_price_sort_puts_no_price_last(recent, sort, order):
    pages = {1: [ad("free", "Сьогодні о 10:00", price=None), ad("x", "Сьогодні о 09:00", price=500),
                 ad("y", "Сьогодні о 08:00", price=100)]}
    ids, _ = recent(pages, "1d", sort=sort)
    assert ids == order
