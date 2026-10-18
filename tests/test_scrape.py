import unittest
from unittest.mock import MagicMock, patch

from scrapers import olx


def card(ad_id, town="Київ"):
    return (f'<div data-cy="l-card" id="{ad_id}">'
            f'<a data-testid="card-title-link" href="/d/obyavlenie/{ad_id}.html">Товар {ad_id}</a>'
            f'<p data-testid="ad-price">100 грн.</p>'
            f'<p data-testid="location-date">{town} - Сьогодні о 10:00</p></div>')


def page(*grids):
    body = "".join(f'<div data-testid="listing-grid">{"".join(cards)}</div>' for cards in grids)
    return f"<html><body>{body}</body></html>"


def fake_get(html):
    response = MagicMock()
    response.status_code = 200
    response.content = html.encode("utf-8")
    return MagicMock(return_value=response)


class ScrapeTest(unittest.TestCase):
    def scrape(self, html, *args, **kwargs):
        get = fake_get(html)
        with patch.object(olx.requests, "get", get):
            result = olx.scrape(*args, **kwargs)
        return result, get

    def test_ignores_cards_from_other_locations_grid(self):
        html = page([card("a"), card("b")], [card("other", "Дніпро")])
        ads, _ = self.scrape(html, "iphone")
        self.assertEqual([ad["id"] for ad in ads], ["a", "b"])

    def test_no_results_ignores_suggested_ads(self):
        html = page([], [card("ad1", "Дніпро"), card("ad2", "Харків")])
        ads, _ = self.scrape(html, "zzqxjwvkpl")
        self.assertEqual(ads, [])

    def test_default_search_url_without_city_and_state(self):
        _, get = self.scrape(page([]), "iphone", 2)
        url = get.call_args.args[0]
        params = get.call_args.kwargs["params"]
        self.assertEqual(url, "https://www.olx.ua/uk/list/q-iphone/")
        self.assertEqual(params["page"], 2)
        self.assertNotIn("search[filter_enum_state][0]", params)

    def test_city_goes_to_path_and_state_to_params(self):
        _, get = self.scrape(page([]), "iphone", city="lviv", state="used", max_price=5000)
        url = get.call_args.args[0]
        params = get.call_args.kwargs["params"]
        self.assertEqual(url, "https://www.olx.ua/uk/lvov/q-iphone/")
        self.assertEqual(params["search[filter_enum_state][0]"], "used")
        self.assertEqual(params["search[filter_float_price:to]"], 5000)


if __name__ == "__main__":
    unittest.main()
