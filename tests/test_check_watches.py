import io
import os
import tempfile
import threading
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

BOT = {}
ROOT = Path(__file__).resolve().parent.parent


def setUpModule():
    os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKENtesttokenTESTTOKENtesttoken")
    path = ROOT / "bot.py"
    source = path.read_text(encoding="utf-8").replace("asyncio.run(main())", "")
    exec(compile(source, str(path), "exec"), BOT)


def make_ad(price=2200):
    return {"id": "909426485", "source": "olx", "name": "Сумка Bagllet", "price": price,
            "currency": "UAH", "price_converted": False, "price_label": None, "town": "Київ",
            "published_date": "11 жовтня 2026 р.", "photo": None, "promoted": False,
            "link": "https://www.olx.ua/d/obyavlenie/sumka-bagllet-ID110gp8.html"}


class WatchesTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        import database
        database.create_table()
        database.create_watches_table()
        database.create_price_history_table()
        database.create_favorites_table()
        database.migrate_price_currency()
        database.save_watch(1, "bagllet сумка", 0, 0)
        self.ads = [make_ad()]
        self.fake_bot = MagicMock()
        self.fake_bot.send_photo = AsyncMock()
        self.fake_bot.send_message = AsyncMock()
        self.patcher = patch.dict(BOT, {
            "bot": self.fake_bot,
            "search": lambda *args, **kwargs: [dict(ad) for ad in self.ads],
            "get_ad_photo": lambda ad: "photo",
        })
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        os.chdir(self.old_cwd)
        self.tmp.cleanup()


class CheckWatchesTest(WatchesTestCase):
    def sent_count(self):
        return self.fake_bot.send_photo.await_count + self.fake_bot.send_message.await_count

    async def test_new_ad_notified_once(self):
        await BOT["check_watches"]()
        await BOT["check_watches"]()
        self.assertEqual(self.sent_count(), 1)

    async def test_failed_send_does_not_repeat_new_ad(self):
        error = TelegramNetworkError(method=None, message="timeout")
        self.fake_bot.send_photo.side_effect = error
        self.fake_bot.send_message.side_effect = error
        await BOT["check_watches"]()
        self.fake_bot.send_photo.reset_mock()
        self.fake_bot.send_message.reset_mock()
        await BOT["check_watches"]()
        self.assertEqual(self.sent_count(), 0)

    async def test_network_error_on_photo_does_not_send_text_copy(self):
        self.fake_bot.send_photo.side_effect = TelegramNetworkError(method=None, message="timeout")
        await BOT["check_watches"]()
        self.fake_bot.send_message.assert_not_awaited()

    async def test_bad_photo_falls_back_to_text(self):
        self.fake_bot.send_photo.side_effect = TelegramBadRequest(method=None, message="IMAGE_PROCESS_FAILED")
        await BOT["check_watches"]()
        self.fake_bot.send_message.assert_awaited_once()

    async def test_failed_ad_does_not_stop_other_ads(self):
        second = make_ad()
        second["id"] = "937533262"
        self.ads.append(second)
        self.fake_bot.send_photo.side_effect = [TelegramNetworkError(method=None, message="timeout"), None]
        await BOT["check_watches"]()
        self.assertEqual(self.fake_bot.send_photo.await_count, 2)

    async def test_price_drop_title_and_no_max_line(self):
        for price in (2500, 2200, 2000):
            self.ads = [make_ad(price)]
            await BOT["check_watches"]()
        caption = self.fake_bot.send_photo.await_args.kwargs["caption"]
        self.assertIn("📉 Подешевшало: 2 200 → 2 000 грн", caption)
        self.assertIn("💰 2 000 грн\n", caption)
        self.assertNotIn("було", caption)

    async def test_photo_is_prepared_outside_event_loop_thread(self):
        threads = []

        def photo(ad):
            threads.append(threading.current_thread())
            return "photo"

        with patch.dict(BOT, {"get_ad_photo": photo}):
            await BOT["check_watches"]()
        self.assertEqual(len(threads), 1)
        self.assertIsNot(threads[0], threading.main_thread())
        self.assertEqual(self.fake_bot.send_photo.await_args.kwargs["photo"], "photo")

    async def test_new_ad_has_no_max_line(self):
        import database
        database.save_price("909426485", "olx", 2500, "UAH")
        await BOT["check_watches"]()
        caption = self.fake_bot.send_photo.await_args_list[0].kwargs["caption"]
        self.assertIn("🆕 Нове оголошення", caption)
        self.assertNotIn("було", caption)


def named_ad(ad_id, name):
    ad = make_ad()
    ad["id"] = ad_id
    ad["name"] = name
    return ad


class GroupedWatchesTest(WatchesTestCase):
    def setUp(self):
        super().setUp()
        import database
        self.db = database
        self.search = MagicMock(side_effect=lambda *args, **kwargs: [dict(ad) for ad in self.ads])
        self.wait = AsyncMock()
        self.send = AsyncMock()
        self.extra = patch.dict(BOT, {"search": self.search, "wait": self.wait, "send_ad_card": self.send})
        self.extra.start()

    def tearDown(self):
        self.extra.stop()
        super().tearDown()

    async def check(self):
        out = io.StringIO()
        with redirect_stdout(out):
            await BOT["check_watches"]()
        return out.getvalue()

    def notified(self):
        return sorted((call.args[0], call.args[1]["id"]) for call in self.send.await_args_list)

    async def test_same_watch_of_two_users_is_one_request_and_both_notified(self):
        self.db.save_watch(2, "bagllet сумка", 0, 0)
        await self.check()
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(self.notified(), [(1, "909426485"), (2, "909426485")])

    async def test_two_users_both_get_price_drop(self):
        self.db.save_watch(2, "bagllet сумка", 0, 0)
        await self.check()
        self.ads = [make_ad(1900)]
        self.send.reset_mock()
        await self.check()
        titles = [call.args[2] for call in self.send.await_args_list]
        self.assertEqual(len(titles), 2)
        self.assertTrue(all("Подешевшало" in title for title in titles))

    async def test_exact_and_plain_watch_share_request_but_exact_filters(self):
        self.db.save_watch(2, "bagllet сумка", 0, 0, exact=True)
        self.db.save_watch(1, "bagllet сумка", 0, 0, exact=True)
        self.ads = [named_ad("a", "Сумка Bagllet шкіряна"), named_ad("b", "Сумочка Bagllet")]
        await self.check()
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(self.notified(), [(1, "a"), (1, "b"), (2, "a")])

    async def test_pause_between_requests_but_not_before_first(self):
        self.db.save_watch(1, "лампа", 0, 0)
        self.db.save_watch(1, "лампа", 500, 0, city="lviv")
        await self.check()
        self.assertEqual(self.search.call_count, 3)
        pauses = [call.args[0] for call in self.wait.await_args_list]
        self.assertEqual(len(pauses), 2)
        self.assertTrue(all(1 <= pause <= 2 for pause in pauses))
        self.assertEqual(self.search.call_args.kwargs["city"], "lviv")

    async def test_timeout_is_retried_with_growing_delay(self):
        results = [BOT["OlxError"]("таймаут"), BOT["OlxError"]("таймаут"), [make_ad()]]
        self.search.side_effect = lambda *args, **kwargs: (
            (_ for _ in ()).throw(results.pop(0)) if isinstance(results[0], Exception) else results.pop(0))
        log = await self.check()
        self.assertEqual(self.search.call_count, 3)
        delays = [call.args[0] for call in self.wait.await_args_list]
        self.assertTrue(2 <= delays[0] < 3 and 4 <= delays[1] < 5)
        self.assertEqual(self.notified(), [(1, "909426485")])
        self.assertIn("повторів — 2", log)

    async def test_stops_after_failed_groups_in_row_with_one_summary_line(self):
        for query in ("a", "b", "c", "d", "e"):
            self.db.save_watch(1, query, 0, 0)
        self.search.side_effect = BOT["OlxError"]("таймаут")
        log = await self.check()
        attempts = len(BOT["WATCH_RETRY_DELAYS"]) + 1
        self.assertEqual(self.search.call_count, BOT["MAX_FAILED_GROUPS_IN_ROW"] * attempts)
        self.assertEqual(log.count("\n"), 1)
        self.assertIn("не вдалося — 3 (таймаут ×3)", log)
        self.assertIn("пропущено — 3", log)

    async def test_one_failed_group_does_not_block_others(self):
        self.db.save_watch(2, "лампа", 0, 0)
        def fake(query, **kwargs):
            if query == "bagllet сумка":
                raise BOT["OlxError"]("HTTP 429")
            return [named_ad("lamp", "Лампа")]
        self.search.side_effect = fake
        log = await self.check()
        self.assertEqual(self.notified(), [(2, "lamp")])
        self.assertIn("не вдалося — 1 (HTTP 429 ×1)", log)

    async def test_no_active_watches_logs_nothing(self):
        self.db.toggle_watch(1)
        self.assertEqual(await self.check(), "")
        self.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
