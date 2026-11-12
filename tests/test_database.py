import pytest
from sqlalchemy import text

import database
import db


def make_ad(**changes):
    ad = {"id": "1", "source": "olx", "name": "Лампа", "price": 500, "currency": "UAH", "price_converted": False,
          "price_label": None, "town": "Київ", "published_date": "11 жовтня 2026 р.",
          "link": "https://www.olx.ua/d/1.html", "photo": None}
    ad.update(changes)
    return ad


def select(sql):
    with db.Session() as session:
        return [tuple(row) for row in session.execute(text(sql))]


def test_save_ad_updates_existing_ad_and_keeps_first_seen():
    database.save_ad(make_ad(), "лампа")
    first_seen = select("SELECT first_seen FROM ads")
    database.save_ad(make_ad(price=400, name="Лампа нова"), "інший запит")
    assert select("SELECT name, price FROM ads") == [("Лампа нова", 400)]
    assert select("SELECT first_seen FROM ads") == first_seen


def test_ad_exists_and_get_link():
    assert not database.ad_exists("1", "olx")
    database.save_ad(make_ad(), "лампа")
    assert database.ad_exists("1", "olx")
    assert database.get_link("1", "olx") == "https://www.olx.ua/d/1.html"
    assert database.get_link("2", "olx") is None


def test_same_watch_is_saved_once():
    database.save_watch(1, "лампа", None, 100)
    database.save_watch(1, "лампа", None, 100)
    watches = database.get_user_watches(1)
    assert len(watches) == 1
    watch = watches[0]
    assert (watch["max_price"], watch["min_price"], watch["city"], watch["state"], watch["exact"]) == (
        0, 100, "", "", 0)


def test_telegram_user_id_above_32_bits():
    user_id = 7_000_000_000
    database.save_watch(user_id, "лампа", None, None)
    assert len(database.get_user_watches(user_id)) == 1


def test_toggle_and_active_watches():
    database.save_watch(1, "лампа", None, None)
    watch_id = database.get_user_watches(1)[0]["id"]
    assert len(database.get_active_watches()) == 1
    database.toggle_watch(watch_id)
    assert database.get_active_watches() == []
    database.toggle_watch(watch_id)
    assert len(database.get_active_watches()) == 1


def test_deleted_watch_id_is_not_reused():
    database.save_watch(1, "лампа", None, None)
    first_id = database.get_user_watches(1)[0]["id"]
    database.delete_watch(first_id)
    database.save_watch(1, "стіл", None, None)
    assert database.get_user_watches(1)[0]["id"] > first_id


def test_price_history_compares_only_same_currency():
    database.save_ad(make_ad(), "лампа")
    database.save_price("1", "olx", 500, "UAH")
    database.save_price("1", "olx", 700, "UAH")
    database.save_price("1", "olx", 20, "USD")
    assert database.get_last_price("1", "olx", "UAH") == 700
    assert database.get_max_price("1", "olx", "UAH") == 700
    assert database.get_last_price("1", "olx", "USD") == 20
    assert database.get_last_price("1", "olx", "EUR") is None
    assert database.get_max_price("1", "olx", "EUR") is None


def test_unknown_currency_never_matches_old_history():
    database.save_ad(make_ad(), "лампа")
    database.save_price("1", "olx", 500, None)
    assert database.get_last_price("1", "olx", None) is None
    assert database.get_max_price("1", "olx", None) is None


def test_favorites():
    database.save_ad(make_ad(), "лампа")
    database.save_favorite(1, "1", "olx")
    database.save_favorite(1, "1", "olx")
    assert database.is_favorite(1, "1", "olx")
    assert not database.is_favorite(2, "1", "olx")
    assert [ad["name"] for ad in database.get_favorites(1)] == ["Лампа"]
    database.delete_favorite(1, "1", "olx")
    assert database.get_favorites(1) == []
    assert not database.is_favorite(1, "1", "olx")


@pytest.mark.parametrize("user_id, query, filters", [
    (1, "диван", {}),
    (1, "диван", {"city": "kyiv"}),
    (1, "диван", {"city": "kyiv", "state": "used", "exact": True}),
])
def test_delete_user_watch_matches_all_filters(user_id, query, filters):
    database.save_watch(1, "диван", 500, None)
    database.save_watch(1, "диван", 500, None, city="kyiv")
    database.save_watch(1, "диван", 500, None, city="kyiv", state="used", exact=True)
    database.delete_user_watch(user_id, query, 500, None, **filters)
    remaining = {(w["city"], w["state"], w["exact"]) for w in database.get_user_watches(1)}
    deleted = (filters.get("city", ""), filters.get("state", ""), int(filters.get("exact", False)))
    assert deleted not in remaining
    assert len(remaining) == 2
