import unittest

from sqlalchemy import text

import database
import db
from tests.db_helper import drop_memory_database, use_memory_database


def make_ad(**changes):
    ad = {"id": "1", "source": "olx", "name": "Лампа", "price": 500, "currency": "UAH", "price_converted": False,
          "price_label": None, "town": "Київ", "published_date": "11 жовтня 2026 р.",
          "link": "https://www.olx.ua/d/1.html", "photo": None}
    ad.update(changes)
    return ad


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        use_memory_database()

    def tearDown(self):
        drop_memory_database()

    def test_save_ad_updates_existing_ad_and_keeps_first_seen(self):
        database.save_ad(make_ad(), "лампа")
        first_seen = self.first_seen()
        database.save_ad(make_ad(price=400, name="Лампа нова"), "інший запит")
        self.assertEqual(self.ad_rows(), [("Лампа нова", 400)])
        self.assertEqual(self.first_seen(), first_seen)

    def first_seen(self):
        with db.Session() as session:
            return session.execute(text("SELECT first_seen FROM ads")).scalar_one()

    def ad_rows(self):
        with db.Session() as session:
            return [tuple(row) for row in session.execute(text("SELECT name, price FROM ads"))]

    def test_ad_exists_and_get_link(self):
        self.assertFalse(database.ad_exists("1", "olx"))
        database.save_ad(make_ad(), "лампа")
        self.assertTrue(database.ad_exists("1", "olx"))
        self.assertEqual(database.get_link("1", "olx"), "https://www.olx.ua/d/1.html")
        self.assertIsNone(database.get_link("2", "olx"))

    def test_same_watch_is_saved_once(self):
        database.save_watch(1, "лампа", None, 100)
        database.save_watch(1, "лампа", None, 100)
        watches = database.get_user_watches(1)
        self.assertEqual(len(watches), 1)
        self.assertEqual((watches[0]["max_price"], watches[0]["min_price"], watches[0]["city"],
                          watches[0]["state"], watches[0]["exact"]), (0, 100, "", "", 0))

    def test_telegram_user_id_above_32_bits(self):
        user_id = 7_000_000_000
        database.save_watch(user_id, "лампа", None, None)
        self.assertEqual(len(database.get_user_watches(user_id)), 1)

    def test_toggle_and_active_watches(self):
        database.save_watch(1, "лампа", None, None)
        watch_id = database.get_user_watches(1)[0]["id"]
        self.assertEqual(len(database.get_active_watches()), 1)
        database.toggle_watch(watch_id)
        self.assertEqual(database.get_active_watches(), [])
        database.toggle_watch(watch_id)
        self.assertEqual(len(database.get_active_watches()), 1)

    def test_deleted_watch_id_is_not_reused(self):
        database.save_watch(1, "лампа", None, None)
        first_id = database.get_user_watches(1)[0]["id"]
        database.delete_watch(first_id)
        database.save_watch(1, "стіл", None, None)
        self.assertGreater(database.get_user_watches(1)[0]["id"], first_id)

    def test_price_history_compares_only_same_currency(self):
        database.save_ad(make_ad(), "лампа")
        database.save_price("1", "olx", 500, "UAH")
        database.save_price("1", "olx", 700, "UAH")
        database.save_price("1", "olx", 20, "USD")
        self.assertEqual(database.get_last_price("1", "olx", "UAH"), 700)
        self.assertEqual(database.get_max_price("1", "olx", "UAH"), 700)
        self.assertEqual(database.get_last_price("1", "olx", "USD"), 20)
        self.assertIsNone(database.get_last_price("1", "olx", "EUR"))
        self.assertIsNone(database.get_max_price("1", "olx", "EUR"))

    def test_unknown_currency_never_matches_old_history(self):
        database.save_ad(make_ad(), "лампа")
        database.save_price("1", "olx", 500, None)
        self.assertIsNone(database.get_last_price("1", "olx", None))
        self.assertIsNone(database.get_max_price("1", "olx", None))

    def test_favorites(self):
        database.save_ad(make_ad(), "лампа")
        database.save_favorite(1, "1", "olx")
        database.save_favorite(1, "1", "olx")
        self.assertTrue(database.is_favorite(1, "1", "olx"))
        self.assertFalse(database.is_favorite(2, "1", "olx"))
        favorites = database.get_favorites(1)
        self.assertEqual([ad["name"] for ad in favorites], ["Лампа"])
        database.delete_favorite(1, "1", "olx")
        self.assertEqual(database.get_favorites(1), [])
        self.assertFalse(database.is_favorite(1, "1", "olx"))


if __name__ == "__main__":
    unittest.main()
