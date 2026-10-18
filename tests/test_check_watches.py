import os
import tempfile
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


class CheckWatchesTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_new_ad_has_no_max_line(self):
        import database
        database.save_price("909426485", "olx", 2500, "UAH")
        await BOT["check_watches"]()
        caption = self.fake_bot.send_photo.await_args_list[0].kwargs["caption"]
        self.assertIn("🆕 Нове оголошення", caption)
        self.assertNotIn("було", caption)


if __name__ == "__main__":
    unittest.main()
