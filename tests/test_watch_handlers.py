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


def make_callback(markup, user_id=1):
    callback = MagicMock()
    callback.from_user.id = user_id
    callback.message.chat.id = user_id
    callback.message.message_id = 10
    callback.message.reply_markup = markup
    callback.message.edit_reply_markup = AsyncMock()
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


if __name__ == "__main__":
    unittest.main()
