import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

BOT = {}
ROOT = Path(__file__).resolve().parent.parent


def setUpModule():
    os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKENtesttokenTESTTOKENtesttoken")
    path = ROOT / "bot.py"
    source = path.read_text(encoding="utf-8").replace("asyncio.run(main())", "")
    exec(compile(source, str(path), "exec"), BOT)


def make_ad():
    return {"id": "909426485", "source": "olx", "name": "Сумка Bagllet", "price": 2200,
            "currency": "UAH", "price_converted": False, "price_label": None, "town": "Київ",
            "published_date": "11 жовтня 2026 р.", "photo": None, "promoted": False,
            "link": "https://www.olx.ua/d/obyavlenie/sumka-bagllet-ID110gp8.html"}


def make_callback(markup=None, user_id=1, data=""):
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = user_id
    callback.message.chat.id = user_id
    callback.message.message_id = 10
    callback.message.reply_markup = markup
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        import database
        self.db = database
        database.create_table()
        database.create_watches_table()
        database.create_price_history_table()
        database.create_favorites_table()
        database.migrate_price_currency()

    def tearDown(self):
        BOT["message_results"].clear()
        os.chdir(self.old_cwd)
        self.tmp.cleanup()


class UnwatchButtonTest(DatabaseTestCase):
    async def test_second_press_deletes_watch(self):
        state = {"ads": [make_ad()], "mode": "search", "query": "bagllet сумка",
                 "min_price": None, "max_price": 3000, "watching": False}
        BOT["message_results"][(1, 10)] = state
        _, markup = BOT["build_ad_card"](make_ad(), 0, 1, watching=False, user_id=1)

        callback = make_callback(markup)
        await BOT["watch_button_handler"](callback)
        self.assertEqual(len(self.db.get_user_watches(1)), 1)
        markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
        self.assertIn("✅ Стежу", button_texts(markup))

        callback = make_callback(markup)
        await BOT["unwatch_button_handler"](callback)
        self.assertEqual(self.db.get_user_watches(1), [])
        self.assertFalse(state["watching"])
        markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
        self.assertIn("🔔 Стежити", button_texts(markup))
        self.assertNotIn("✅ Стежу", button_texts(markup))
        callback.message.answer.assert_awaited_once_with("Більше не стежу за «bagllet сумка»")

    async def test_deletes_only_matching_watch(self):
        self.db.save_watch(1, "bagllet сумка", None, None)
        self.db.save_watch(1, "bagllet сумка", 3000, None)
        self.db.save_watch(2, "bagllet сумка", None, None)
        self.db.delete_user_watch(1, "bagllet сумка", None, None)
        self.assertEqual([w["max_price"] for w in self.db.get_user_watches(1)], [3000])
        self.assertEqual(len(self.db.get_user_watches(2)), 1)

    async def test_stale_message(self):
        _, markup = BOT["build_ad_card"](make_ad(), 0, 1, watching=True, user_id=1)
        callback = make_callback(markup)
        await BOT["unwatch_button_handler"](callback)
        callback.answer.assert_awaited_once_with(BOT["STALE_TEXT"])


class WatchesListTest(DatabaseTestCase):
    def add_watches(self, count, user_id=1):
        for number in range(1, count + 1):
            self.db.save_watch(user_id, f"запит {number}", number * 1000, None)

    def edited(self, callback):
        args = callback.message.edit_text.await_args
        return args.args[0], args.kwargs["reply_markup"]

    def test_empty(self):
        self.assertEqual(BOT["build_watches_list"]([], 0), (BOT["NO_WATCHES_TEXT"], None))

    def test_newest_first_five_per_page(self):
        self.add_watches(7)
        text, markup = BOT["build_watches_list"](self.db.get_user_watches(1), 0)
        self.assertTrue(text.startswith("📌 Мої пошуки · 7"))
        self.assertIn("1. запит 7\n💰 до 7 000 грн · 🟢 Активна", text)
        self.assertIn("5. запит 3", text)
        self.assertNotIn("запит 2", text)
        self.assertEqual(len(markup.inline_keyboard), 6)
        self.assertEqual(button_texts(markup)[:2], ["1. ⏸ Пауза", "1. 🗑 Видалити"])
        self.assertEqual(button_texts(markup)[-3:], ["◀️", "1 / 2", "▶️"])

    def test_second_page_continues_numbering(self):
        self.add_watches(7)
        text, markup = BOT["build_watches_list"](self.db.get_user_watches(1), 1)
        self.assertIn("6. запит 2", text)
        self.assertIn("7. запит 1", text)
        self.assertIn("2 / 2", button_texts(markup))

    def test_single_page_has_no_navigation(self):
        self.add_watches(5)
        _, markup = BOT["build_watches_list"](self.db.get_user_watches(1), 0)
        self.assertEqual(len(markup.inline_keyboard), 5)

    async def test_pause_toggles_and_keeps_page(self):
        self.add_watches(7)
        watch_id = self.db.get_user_watches(1)[5]["id"]
        callback = make_callback(data=f"pause:{watch_id}:1")
        await BOT["pause_handler"](callback)
        self.assertEqual(self.db.get_watch(watch_id)["is_active"], 0)
        text, markup = self.edited(callback)
        self.assertIn("6. запит 2\n💰 до 2 000 грн · ⏸ На паузі", text)
        self.assertIn("6. ▶️ Увімкнути", button_texts(markup))

    async def test_delete_last_on_page_moves_back(self):
        self.add_watches(6)
        watch_id = self.db.get_user_watches(1)[5]["id"]
        callback = make_callback(data=f"delete:{watch_id}:1")
        await BOT["delete_handler"](callback)
        self.assertIsNone(self.db.get_watch(watch_id))
        text, markup = self.edited(callback)
        self.assertIn("📌 Мої пошуки · 5", text)
        self.assertNotIn("◀️", button_texts(markup))
        callback.answer.assert_awaited_once_with("Видалено «запит 1»")

    async def test_delete_all(self):
        self.add_watches(1)
        watch_id = self.db.get_user_watches(1)[0]["id"]
        callback = make_callback(data=f"delete:{watch_id}:0")
        await BOT["delete_handler"](callback)
        callback.message.edit_text.assert_awaited_once_with(BOT["NO_WATCHES_TEXT"], reply_markup=None)

    async def test_other_users_watch_is_untouched(self):
        self.add_watches(1, user_id=2)
        watch_id = self.db.get_user_watches(2)[0]["id"]
        for data in (f"delete:{watch_id}:0", f"pause:{watch_id}:0"):
            callback = make_callback(data=data)
            handler = BOT["delete_handler"] if data.startswith("delete") else BOT["pause_handler"]
            await handler(callback)
            callback.answer.assert_awaited_once_with(BOT["STALE_TEXT"])
        self.assertEqual(self.db.get_watch(watch_id)["is_active"], 1)

    async def test_old_card_button_is_stale(self):
        self.add_watches(1)
        watch_id = self.db.get_user_watches(1)[0]["id"]
        callback = make_callback(data=f"delete:{watch_id}")
        await BOT["delete_handler"](callback)
        callback.answer.assert_awaited_once_with(BOT["STALE_TEXT"])
        self.assertIsNotNone(self.db.get_watch(watch_id))

    async def test_page_navigation(self):
        self.add_watches(7)
        callback = make_callback(data="wpage:1")
        await BOT["watches_page_handler"](callback)
        self.assertIn("6. запит 2", self.edited(callback)[0])
        for data in ("wpage:2", "wpage:-1"):
            callback = make_callback(data=data)
            await BOT["watches_page_handler"](callback)
            callback.answer.assert_awaited_once_with("Це край списку")
            callback.message.edit_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
