import pytest

import database
from tests.helpers import button_texts, make_ad, make_callback


def add_watches(count, user_id=1):
    for number in range(1, count + 1):
        database.save_watch(user_id, f"запит {number}", number * 1000, None)


def edited(callback):
    args = callback.message.edit_text.await_args
    return args.args[0], args.kwargs["reply_markup"]


async def test_second_press_deletes_watch(app):
    state = {"ads": [make_ad()], "mode": "search", "query": "bagllet сумка",
             "min_price": None, "max_price": 3000, "watching": False}
    app["message_results"][(1, 10)] = state
    _, markup = app["build_ad_card"](make_ad(), 0, 1, watching=False, user_id=1)

    callback = make_callback(markup)
    await app["watch_button_handler"](callback)
    assert len(database.get_user_watches(1)) == 1
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert "✅ Стежу" in button_texts(markup)

    callback = make_callback(markup)
    await app["unwatch_button_handler"](callback)
    assert database.get_user_watches(1) == []
    assert state["watching"] is False
    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    assert "🔔 Стежити" in button_texts(markup)
    assert "✅ Стежу" not in button_texts(markup)
    callback.message.answer.assert_awaited_once_with("Більше не стежу за «bagllet сумка»")


def test_deletes_only_matching_watch():
    database.save_watch(1, "bagllet сумка", None, None)
    database.save_watch(1, "bagllet сумка", 3000, None)
    database.save_watch(2, "bagllet сумка", None, None)
    database.delete_user_watch(1, "bagllet сумка", None, None)
    assert [w["max_price"] for w in database.get_user_watches(1)] == [3000]
    assert len(database.get_user_watches(2)) == 1


async def test_stale_message(app):
    _, markup = app["build_ad_card"](make_ad(), 0, 1, watching=True, user_id=1)
    callback = make_callback(markup)
    await app["unwatch_button_handler"](callback)
    callback.answer.assert_awaited_once_with(app["STALE_TEXT"])


def test_empty_list(app):
    assert app["build_watches_list"]([], 0) == (app["NO_WATCHES_TEXT"], None)


def test_newest_first_five_per_page(app):
    add_watches(7)
    text, markup = app["build_watches_list"](database.get_user_watches(1), 0)
    assert text.startswith("📌 Мої пошуки · 7")
    assert "1. запит 7\n💰 до 7 000 грн · 🟢 Активна" in text
    assert "5. запит 3" in text
    assert "запит 2" not in text
    assert len(markup.inline_keyboard) == 6
    assert button_texts(markup)[:2] == ["1. ⏸ Пауза", "1. 🗑 Видалити"]
    assert button_texts(markup)[-3:] == ["◀️", "1 / 2", "▶️"]


def test_second_page_continues_numbering(app):
    add_watches(7)
    text, markup = app["build_watches_list"](database.get_user_watches(1), 1)
    assert "6. запит 2" in text
    assert "7. запит 1" in text
    assert "2 / 2" in button_texts(markup)


def test_single_page_has_no_navigation(app):
    add_watches(5)
    _, markup = app["build_watches_list"](database.get_user_watches(1), 0)
    assert len(markup.inline_keyboard) == 5


async def test_pause_toggles_and_keeps_page(app):
    add_watches(7)
    watch_id = database.get_user_watches(1)[5]["id"]
    callback = make_callback(data=f"pause:{watch_id}:1")
    await app["pause_handler"](callback)
    assert database.get_watch(watch_id)["is_active"] == 0
    text, markup = edited(callback)
    assert "6. запит 2\n💰 до 2 000 грн · ⏸ На паузі" in text
    assert "6. ▶️ Увімкнути" in button_texts(markup)


async def test_delete_last_on_page_moves_back(app):
    add_watches(6)
    watch_id = database.get_user_watches(1)[5]["id"]
    callback = make_callback(data=f"delete:{watch_id}:1")
    await app["delete_handler"](callback)
    assert database.get_watch(watch_id) is None
    text, markup = edited(callback)
    assert "📌 Мої пошуки · 5" in text
    assert "◀️" not in button_texts(markup)
    callback.answer.assert_awaited_once_with("Видалено «запит 1»")


async def test_delete_all(app):
    add_watches(1)
    watch_id = database.get_user_watches(1)[0]["id"]
    callback = make_callback(data=f"delete:{watch_id}:0")
    await app["delete_handler"](callback)
    callback.message.edit_text.assert_awaited_once_with(app["NO_WATCHES_TEXT"], reply_markup=None)


@pytest.mark.parametrize("action", ["delete", "pause"])
async def test_other_users_watch_is_untouched(app, action):
    add_watches(1, user_id=2)
    watch_id = database.get_user_watches(2)[0]["id"]
    callback = make_callback(data=f"{action}:{watch_id}:0")
    await app[f"{action}_handler"](callback)
    callback.answer.assert_awaited_once_with(app["STALE_TEXT"])
    assert database.get_watch(watch_id)["is_active"] == 1


async def test_old_card_button_is_stale(app):
    add_watches(1)
    watch_id = database.get_user_watches(1)[0]["id"]
    callback = make_callback(data=f"delete:{watch_id}")
    await app["delete_handler"](callback)
    callback.answer.assert_awaited_once_with(app["STALE_TEXT"])
    assert database.get_watch(watch_id) is not None


async def test_page_navigation(app):
    add_watches(7)
    callback = make_callback(data="wpage:1")
    await app["watches_page_handler"](callback)
    assert "6. запит 2" in edited(callback)[0]
    for data in ("wpage:2", "wpage:-1"):
        callback = make_callback(data=data)
        await app["watches_page_handler"](callback)
        callback.answer.assert_awaited_once_with("Це край списку")
        callback.message.edit_text.assert_not_awaited()
