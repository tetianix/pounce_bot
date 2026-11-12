from unittest.mock import MagicMock, patch

import pytest


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(app):
    fake_clock = Clock()
    with patch.dict(app, {"monotonic": fake_clock}):
        yield fake_clock


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


@pytest.fixture
def save(app, clock):
    return lambda chat_id, message_id: app["save_results"](message(chat_id, message_id),
                                                          {"ads": [], "mode": "search"})


@pytest.fixture
def get(app, clock):
    return lambda chat_id, message_id: app["get_results"](callback(chat_id, message_id))


def test_state_expires_after_ttl(app, clock, save, get):
    save(1, 10)
    clock.now += app["RESULTS_TTL_SECONDS"] - 1
    assert get(1, 10) is not None
    clock.now += app["RESULTS_TTL_SECONDS"]
    assert get(1, 10) is None
    assert app["message_results"] == {}


def test_using_state_extends_its_life(app, clock, save, get):
    save(1, 10)
    for _ in range(3):
        clock.now += app["RESULTS_TTL_SECONDS"] - 60
        assert get(1, 10) is not None


def test_new_save_drops_expired_states_of_everyone(app, clock, save):
    save(1, 10)
    save(2, 20)
    clock.now += app["RESULTS_TTL_SECONDS"]
    save(3, 30)
    assert list(app["message_results"]) == [(3, 30)]


def test_per_chat_limit_drops_oldest_of_that_chat(app, save, get):
    save(2, 1)
    limit = app["MAX_RESULTS_PER_CHAT"]
    for message_id in range(1, limit + 3):
        save(1, message_id)
    own = [key[1] for key in app["message_results"] if key[0] == 1]
    assert own == list(range(3, limit + 3))
    assert get(2, 1) is not None
    assert get(1, 1) is None


def test_recently_used_state_survives_per_chat_limit(app, save, get):
    for message_id in range(1, app["MAX_RESULTS_PER_CHAT"] + 1):
        save(1, message_id)
    get(1, 1)
    save(1, 100)
    assert get(1, 1) is not None
    assert get(1, 2) is None


def test_global_limit(app, save, get):
    for chat_id in range(app["MAX_STORED_RESULTS"] + 5):
        save(chat_id, 1)
    assert len(app["message_results"]) == app["MAX_STORED_RESULTS"]
    assert get(0, 1) is None
