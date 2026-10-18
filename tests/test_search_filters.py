import json
from unittest.mock import AsyncMock, MagicMock, patch

from tests.test_watch_handlers import BOT, DatabaseTestCase, button_texts, make_ad, make_callback, setUpModule

__all__ = ["setUpModule"]


def make_message(data=None, user_id=1):
    message = MagicMock()
    message.from_user.id = user_id
    message.chat.id = user_id
    message.web_app_data.data = json.dumps(data)
    message.answer = AsyncMock()
    card = MagicMock()
    card.chat.id = user_id
    card.message_id = 10
    message.answer_photo = AsyncMock(return_value=card)
    return message


def named_ad(ad_id, name):
    ad = make_ad()
    ad["id"] = ad_id
    ad["name"] = name
    return ad


class WebappFiltersTest(DatabaseTestCase):
    async def send(self, data):
        run_search = AsyncMock()
        with patch.dict(BOT, {"run_search": run_search}):
            await BOT["webapp_handler"](make_message(data))
        return run_search.await_args.args

    async def test_city_state_exact_passed_to_search(self):
        args = await self.send({"query": "iphone", "city": "lviv", "state": "used", "exact": True})
        self.assertEqual(args[-3:], ("lviv", "used", True))

    async def test_without_new_fields_works_as_before(self):
        args = await self.send({"query": "iphone", "min_price": None, "max_price": 5000, "sort": "cheap"})
        self.assertEqual(args[-3:], (None, None, False))

    async def test_bad_values_are_ignored(self):
        args = await self.send({"query": "iphone", "city": "moscow", "state": "broken", "exact": "yes"})
        self.assertEqual(args[-3:], (None, None, False))
        args = await self.send({"query": "iphone", "city": "all", "state": "any", "exact": 1})
        self.assertEqual(args[-3:], (None, None, False))

    async def test_watch_saved_with_filters(self):
        message = make_message({"query": "iphone", "city": "kyiv", "state": "new", "exact": True, "watch": True})
        with patch.dict(BOT, {"run_search": AsyncMock()}):
            await BOT["webapp_handler"](message)
        watch = self.db.get_user_watches(1)[0]
        self.assertEqual((watch["city"], watch["state"], watch["exact"]), ("kyiv", "new", 1))
        self.assertIn("Київ, нове, точний збіг", message.answer.await_args.args[0])


class RunSearchFiltersTest(DatabaseTestCase):
    async def search_with(self, ads, **kwargs):
        search = MagicMock(return_value=ads)
        message = make_message()
        with patch.dict(BOT, {"search": search, "get_ad_photo": lambda ad: "photo"}):
            await BOT["run_search"](message, "iphone 13", **kwargs)
        return search, message

    async def test_passes_city_and_state_to_search(self):
        search, _ = await self.search_with([make_ad()], city="odesa", state="used")
        self.assertEqual(search.call_args.kwargs["city"], "odesa")
        self.assertEqual(search.call_args.kwargs["state"], "used")
        state = BOT["message_results"][(1, 10)]
        self.assertEqual((state["city"], state["state"], state["exact"]), ("odesa", "used", False))

    async def test_exact_keeps_only_titles_with_all_words(self):
        ads = [named_ad("a", "iPhone 13 Pro"), named_ad("b", "iPhone 12"), named_ad("c", "Чохол 13 для iphone")]
        await self.search_with(ads, exact=True)
        state = BOT["message_results"][(1, 10)]
        self.assertEqual([ad["id"] for ad in state["ads"]], ["a", "c"])

    async def test_nothing_found_with_filters_suggests_removing_them(self):
        _, message = await self.search_with([named_ad("b", "iPhone 12")], exact=True)
        self.assertIn("прибрати частину фільтрів", message.answer.await_args_list[-1].args[0])


class RunSearchOlxDownTest(DatabaseTestCase):
    async def test_olx_error_is_not_reported_as_nothing_found(self):
        search = MagicMock(side_effect=BOT["OlxError"]("таймаут"))
        message = make_message()
        with patch.dict(BOT, {"search": search}):
            await BOT["run_search"](message, "iphone")
        texts = [call.args[0] for call in message.answer.await_args_list]
        self.assertEqual(texts[-1], BOT["OLX_DOWN_TEXT"])
        self.assertFalse(any("Нічого не знайдено" in text for text in texts))
        message.answer.return_value.delete.assert_awaited()


class WatchButtonFiltersTest(DatabaseTestCase):
    async def test_watch_and_unwatch_use_filters_from_card(self):
        self.db.save_watch(1, "iphone", None, None)
        state = {"ads": [make_ad()], "mode": "search", "query": "iphone", "min_price": None, "max_price": None,
                 "city": "kyiv", "state": "used", "exact": True, "watching": False}
        BOT["message_results"][(1, 10)] = state
        _, markup = BOT["build_ad_card"](make_ad(), 0, 1, watching=False, user_id=1)

        callback = make_callback(markup)
        await BOT["watch_button_handler"](callback)
        rows = [(w["city"], w["state"], w["exact"]) for w in self.db.get_user_watches(1)]
        self.assertEqual(rows, [("kyiv", "used", 1), ("", "", 0)])

        markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
        await BOT["unwatch_button_handler"](make_callback(markup))
        rows = [(w["city"], w["state"], w["exact"]) for w in self.db.get_user_watches(1)]
        self.assertEqual(rows, [("", "", 0)])


class CheckWatchesFiltersTest(DatabaseTestCase):
    async def test_searches_with_watch_filters(self):
        self.db.save_watch(1, "iphone 13", None, None, city="lviv", state="new", exact=True)
        ads = [named_ad("a", "iPhone 13"), named_ad("b", "iPhone 12")]
        search = MagicMock(side_effect=lambda *args, **kwargs: [dict(ad) for ad in ads])
        send = AsyncMock()
        with patch.dict(BOT, {"search": search, "send_ad_card": send}):
            await BOT["check_watches"]()
        self.assertEqual(search.call_args.kwargs["city"], "lviv")
        self.assertEqual(search.call_args.kwargs["state"], "new")
        self.assertEqual([call.args[1]["id"] for call in send.await_args_list], ["a"])

    async def test_watch_without_filters_searches_all_ukraine(self):
        self.db.save_watch(1, "iphone", None, None)
        search = MagicMock(return_value=[])
        with patch.dict(BOT, {"search": search}):
            await BOT["check_watches"]()
        self.assertEqual((search.call_args.kwargs["city"], search.call_args.kwargs["state"]), (None, None))


class WatchesListFiltersTest(DatabaseTestCase):
    def test_filters_line_only_when_set(self):
        self.db.save_watch(1, "диван", None, None)
        self.db.save_watch(1, "iphone", 20000, None, city="kharkiv", state="used", exact=True)
        text, markup = BOT["build_watches_list"](self.db.get_user_watches(1), 0)
        self.assertIn("1. iphone\n💰 до 20 000 грн · 🟢 Активна\n🔎 Харків · вживане · точний збіг", text)
        self.assertTrue(text.endswith("2. диван\n💰 будь-яка · 🟢 Активна"))
        self.assertIn("1. 🗑 Видалити", button_texts(markup))

    def test_watch_message_lists_filters(self):
        text = BOT["build_watch_message"]("iphone", None, 5000, "odesa", None, False)
        self.assertTrue(text.startswith("Стежу за «iphone», до 5 000 грн, Одеса 🐾"))
