import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import core
from core import search_recent

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)


def ad(ad_id, published_date, price=100, promoted=False):
    return {"source": "olx", "id": ad_id, "published_date": published_date, "price": price, "promoted": promoted}


class FakeSearch:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, query, page, min_price=None, max_price=None, sort="new"):
        self.calls.append({"page": page, "min_price": min_price, "max_price": max_price, "sort": sort})
        return [dict(item) for item in self.pages.get(page, [])]


class SearchRecentTest(unittest.TestCase):
    def run_search(self, pages, period, now=NOW, **kwargs):
        fake = FakeSearch(pages)
        with patch.object(core, "search", fake):
            result = search_recent("диван", period, now=now, **kwargs)
        return [item["id"] for item in result], fake.calls

    def test_three_days_includes_boundary_and_stops_on_old(self):
        pages = {
            1: [ad("a", "Сьогодні о 10:00"), ad("b", "Вчора о 10:00"),
                ad("c", "09 жовтня 2026 р."), ad("d", "08 жовтня 2026 р.")],
            2: [ad("e", "Сьогодні о 09:00")],
        }
        ids, calls = self.run_search(pages, "3d")
        self.assertEqual(ids, ["a", "b", "c"])
        self.assertEqual([call["page"] for call in calls], [1])

    def test_one_day_only_today(self):
        pages = {1: [ad("a", "Сьогодні о 10:00"), ad("b", "Вчора о 23:00")]}
        ids, _ = self.run_search(pages, "1d")
        self.assertEqual(ids, ["a"])

    def test_old_promoted_ad_does_not_stop_paging(self):
        pages = {
            1: [ad("top", "01 жовтня 2026 р.", promoted=True), ad("a", "Сьогодні о 10:00")],
            2: [ad("b", "Сьогодні о 08:00"), ad("old", "01 жовтня 2026 р.")],
            3: [ad("c", "Сьогодні о 07:00")],
        }
        ids, calls = self.run_search(pages, "1d")
        self.assertEqual(ids, ["a", "b"])
        self.assertEqual([call["page"] for call in calls], [1, 2])

    def test_repeated_page_stops_without_duplicates(self):
        page = [ad("a", "Сьогодні о 10:00"), ad("b", "Сьогодні о 09:00")]
        ids, calls = self.run_search({1: page, 2: page, 3: page}, "7d")
        self.assertEqual(ids, ["a", "b"])
        self.assertEqual([call["page"] for call in calls], [1, 2])

    def test_stops_after_max_pages(self):
        pages = {n: [ad(f"p{n}", "Сьогодні о 10:00")] for n in range(1, 10)}
        ids, calls = self.run_search(pages, "7d")
        self.assertEqual(len(calls), core.MAX_PERIOD_PAGES)
        self.assertEqual(len(ids), core.MAX_PERIOD_PAGES)

    def test_unparsed_date_is_skipped(self):
        pages = {1: [ad("a", "Сьогодні о 10:00"), ad("weird", "щось незрозуміле")], 2: [ad("b", "Сьогодні о 09:00")]}
        ids, calls = self.run_search(pages, "1d")
        self.assertEqual(ids, ["a"])
        self.assertEqual([call["page"] for call in calls], [1])

    def test_today_follows_kyiv_calendar_after_midnight(self):
        late = datetime(2026, 10, 11, 22, 30, tzinfo=timezone.utc)
        pages = {1: [ad("a", "Сьогодні о 00:30"), ad("b", "Вчора о 23:50")]}
        ids, _ = self.run_search(pages, "1d", now=late)
        self.assertEqual(ids, ["a"])

    def test_always_asks_olx_for_newest_and_passes_prices(self):
        _, calls = self.run_search({1: [ad("a", "Сьогодні о 10:00")]}, "1d",
                                   min_price=100, max_price=500, sort="cheap")
        self.assertEqual(calls[0]["sort"], "new")
        self.assertEqual((calls[0]["min_price"], calls[0]["max_price"]), (100, 500))

    def test_sort_new_puts_latest_day_first(self):
        pages = {1: [ad("old", "10 жовтня 2026 р."), ad("new", "Сьогодні о 10:00")]}
        ids, _ = self.run_search(pages, "3d")
        self.assertEqual(ids, ["new", "old"])

    def test_sort_cheap_puts_no_price_last(self):
        pages = {1: [ad("free", "Сьогодні о 10:00", price=None), ad("x", "Сьогодні о 09:00", price=500),
                     ad("y", "Сьогодні о 08:00", price=100)]}
        ids, _ = self.run_search(pages, "1d", sort="cheap")
        self.assertEqual(ids, ["y", "x", "free"])

    def test_sort_expensive_puts_no_price_last(self):
        pages = {1: [ad("free", "Сьогодні о 10:00", price=None), ad("x", "Сьогодні о 09:00", price=500),
                     ad("y", "Сьогодні о 08:00", price=100)]}
        ids, _ = self.run_search(pages, "1d", sort="expensive")
        self.assertEqual(ids, ["x", "y", "free"])


if __name__ == "__main__":
    unittest.main()
