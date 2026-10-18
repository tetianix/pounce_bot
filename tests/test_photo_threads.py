import threading
from unittest.mock import AsyncMock, MagicMock, patch

from tests.test_search_filters import make_message, named_ad
from tests.test_watch_handlers import BOT, DatabaseTestCase, make_callback, setUpModule

__all__ = ["setUpModule"]


class PhotoThreadTest(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.threads = []

        def spy(name):
            def load(value):
                self.threads.append(threading.current_thread())
                return f"{name}:{value['id'] if isinstance(value, dict) else value}"
            return load

        self.patcher = patch.dict(BOT, {"get_ad_photo": spy("ad"), "load_photo": spy("url")})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def assert_off_main_thread(self):
        self.assertEqual(len(self.threads), 1)
        self.assertIsNot(self.threads[0], threading.main_thread())

    def callback(self, data):
        callback = make_callback(data=data)
        callback.message.edit_media = AsyncMock()
        return callback

    def edited_photo(self, callback):
        return callback.message.edit_media.await_args.kwargs["media"].media

    async def test_first_search_card(self):
        message = make_message()
        with patch.dict(BOT, {"search": MagicMock(return_value=[named_ad("a", "Лампа")])}):
            await BOT["run_search"](message, "лампа")
        self.assert_off_main_thread()
        self.assertEqual(message.answer_photo.await_args.kwargs["photo"], "ad:a")

    async def test_favorites_card(self):
        message = make_message()
        with patch.dict(BOT, {"get_favorites": lambda user_id: [named_ad("f", "Лампа")]}):
            await BOT["saved_handler"](message)
        self.assert_off_main_thread()
        self.assertEqual(message.answer_photo.await_args.kwargs["photo"], "ad:f")

    async def test_carousel_navigation(self):
        BOT["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "search"}
        callback = self.callback("nav:1")
        await BOT["nav_handler"](callback)
        self.assert_off_main_thread()
        self.assertEqual(self.edited_photo(callback), "ad:b")

    async def test_details_gallery(self):
        BOT["message_results"][(1, 10)] = {
            "ads": [named_ad("a", "A")], "mode": "search",
            "details": {"index": 0, "photos": ["https://x/1.jpg", "https://x/2.jpg"], "caption": "опис"},
        }
        callback = self.callback("photo:1")
        await BOT["photo_handler"](callback)
        self.assert_off_main_thread()
        self.assertEqual(self.edited_photo(callback), "url:https://x/2.jpg")

    async def test_card_after_removing_from_favorites(self):
        BOT["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "fav"}
        callback = self.callback("favdel:0")
        await BOT["favdel_handler"](callback)
        self.assert_off_main_thread()
        self.assertEqual(self.edited_photo(callback), "ad:b")
