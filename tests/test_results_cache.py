import unittest
from unittest.mock import MagicMock, patch

from tests.test_watch_handlers import BOT, setUpModule

__all__ = ["setUpModule"]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def message(chat_id, message_id):
    item = MagicMock()
    item.chat.id = chat_id
    item.message_id = message_id
    return item


def callback(chat_id, message_id):
    item = MagicMock()
    item.message.chat.id = chat_id
    item.message.message_id = message_id
    return item


class ResultsCacheTest(unittest.TestCase):
    def setUp(self):
        BOT["message_results"].clear()
        self.clock = Clock()
        self.patcher = patch.dict(BOT, {"monotonic": self.clock})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        BOT["message_results"].clear()

    def save(self, chat_id, message_id):
        BOT["save_results"](message(chat_id, message_id), {"ads": [], "mode": "search"})

    def get(self, chat_id, message_id):
        return BOT["get_results"](callback(chat_id, message_id))

    def test_state_expires_after_ttl(self):
        self.save(1, 10)
        self.clock.now += BOT["RESULTS_TTL_SECONDS"] - 1
        self.assertIsNotNone(self.get(1, 10))
        self.clock.now += BOT["RESULTS_TTL_SECONDS"]
        self.assertIsNone(self.get(1, 10))
        self.assertEqual(BOT["message_results"], {})

    def test_using_state_extends_its_life(self):
        self.save(1, 10)
        for _ in range(3):
            self.clock.now += BOT["RESULTS_TTL_SECONDS"] - 60
            self.assertIsNotNone(self.get(1, 10))

    def test_new_save_drops_expired_states_of_everyone(self):
        self.save(1, 10)
        self.save(2, 20)
        self.clock.now += BOT["RESULTS_TTL_SECONDS"]
        self.save(3, 30)
        self.assertEqual(list(BOT["message_results"]), [(3, 30)])

    def test_per_chat_limit_drops_oldest_of_that_chat(self):
        self.save(2, 1)
        limit = BOT["MAX_RESULTS_PER_CHAT"]
        for message_id in range(1, limit + 3):
            self.save(1, message_id)
        own = [key[1] for key in BOT["message_results"] if key[0] == 1]
        self.assertEqual(own, list(range(3, limit + 3)))
        self.assertIsNotNone(self.get(2, 1))
        self.assertIsNone(self.get(1, 1))

    def test_recently_used_state_survives_per_chat_limit(self):
        limit = BOT["MAX_RESULTS_PER_CHAT"]
        for message_id in range(1, limit + 1):
            self.save(1, message_id)
        self.get(1, 1)
        self.save(1, 100)
        self.assertIsNotNone(self.get(1, 1))
        self.assertIsNone(self.get(1, 2))

    def test_global_limit(self):
        for chat_id in range(BOT["MAX_STORED_RESULTS"] + 5):
            self.save(chat_id, 1)
        self.assertEqual(len(BOT["message_results"]), BOT["MAX_STORED_RESULTS"])
        self.assertIsNone(self.get(0, 1))


if __name__ == "__main__":
    unittest.main()
