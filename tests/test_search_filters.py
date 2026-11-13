from unittest.mock import AsyncMock, patch

import pytest

import database
from tests.helpers import button_texts, make_ad, make_callback, make_message, named_ad, olx_down


@pytest.fixture
def run_search(app):
    fake = AsyncMock()
    with patch.dict(app, {"run_search": fake}):
        yield fake


@pytest.fixture
def olx_search(fake_api):
    return fake_api


async def send_form(app, run_search, data):
    await app["webapp_handler"](make_message(data))
    return run_search.await_args.args


async def test_city_state_exact_passed_to_search(app, run_search):
    args = await send_form(app, run_search, {"query": "iphone", "city": "lviv", "state": "used", "exact": True})
    assert args[-3:] == ("lviv", "used", True)


async def test_without_new_fields_works_as_before(app, run_search):
    args = await send_form(app, run_search, {"query": "iphone", "min_price": None, "max_price": 5000, "sort": "cheap"})
    assert args[-3:] == (None, None, False)


@pytest.mark.parametrize("data", [
    {"query": "iphone", "city": "moscow", "state": "broken", "exact": "yes"},
    {"query": "iphone", "city": "all", "state": "any", "exact": 1},
], ids=["unknown-values", "all-and-any"])
async def test_bad_values_are_ignored(app, run_search, data):
    args = await send_form(app, run_search, data)
    assert args[-3:] == (None, None, False)


async def test_watch_saved_with_filters(app, run_search):
    message = make_message({"query": "iphone", "city": "kyiv", "state": "new", "exact": True, "watch": True})
    await app["webapp_handler"](message)
    watch = database.get_user_watches(1)[0]
    assert (watch["city"], watch["state"], watch["exact"]) == ("kyiv", "new", 1)
    assert "Київ, нове, точний збіг" in message.answer.await_args.args[0]


async def test_run_search_passes_city_and_state_to_search(app, olx_search):
    olx_search.ads = [make_ad()]
    await app["run_search"](make_message(), "iphone 13", city="odesa", state="used")
    assert olx_search.searches[0]["city"] == "odesa"
    assert olx_search.searches[0]["state"] == "used"
    state = app["message_results"][(1, 10)]
    assert (state["city"], state["state"], state["exact"]) == ("odesa", "used", False)


async def test_exact_is_left_to_api(app, olx_search):
    olx_search.ads = [named_ad("a", "iPhone 13 Pro"), named_ad("c", "Чохол 13 для iphone")]
    await app["run_search"](make_message(), "iphone 13", exact=True)
    assert olx_search.searches[0]["exact"] == "true"
    assert [ad["id"] for ad in app["message_results"][(1, 10)]["ads"]] == ["a", "c"]


async def test_nothing_found_with_filters_suggests_removing_them(app, olx_search):
    olx_search.ads = []
    message = make_message()
    await app["run_search"](message, "iphone 13", exact=True)
    assert "прибрати частину фільтрів" in message.answer.await_args_list[-1].args[0]


async def test_olx_error_is_not_reported_as_nothing_found(app, olx_search):
    olx_search.script = [olx_down()]
    message = make_message()
    await app["run_search"](message, "iphone")
    texts = [call.args[0] for call in message.answer.await_args_list]
    assert texts[-1] == app["OLX_DOWN_TEXT"]
    assert not any("Нічого не знайдено" in text for text in texts)
    message.answer.return_value.delete.assert_awaited()


async def test_watch_and_unwatch_use_filters_from_card(app):
    database.save_watch(1, "iphone", None, None)
    state = {"ads": [make_ad()], "mode": "search", "query": "iphone", "min_price": None, "max_price": None,
             "city": "kyiv", "state": "used", "exact": True, "watching": False}
    app["message_results"][(1, 10)] = state
    _, markup = app["build_ad_card"](make_ad(), 0, 1, watching=False, user_id=1)

    callback = make_callback(markup)
    await app["watch_button_handler"](callback)
    rows = [(w["city"], w["state"], w["exact"]) for w in database.get_user_watches(1)]
    assert rows == [("kyiv", "used", 1), ("", "", 0)]

    markup = callback.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    await app["unwatch_button_handler"](make_callback(markup))
    rows = [(w["city"], w["state"], w["exact"]) for w in database.get_user_watches(1)]
    assert rows == [("", "", 0)]


async def test_check_watches_searches_with_watch_filters(app, olx_search):
    database.save_watch(1, "iphone 13", None, None, city="lviv", state="new", exact=True)
    ads = [named_ad("a", "iPhone 13"), named_ad("b", "iPhone 12")]
    olx_search.ads = ads
    send = AsyncMock()
    with patch.dict(app, {"send_ad_card": send}):
        await app["check_watches"]()
    assert olx_search.searches[0]["city"] == "lviv"
    assert olx_search.searches[0]["state"] == "new"
    assert [call.args[1]["id"] for call in send.await_args_list] == ["a"]


async def test_check_watches_without_filters_searches_all_ukraine(app, olx_search):
    database.save_watch(1, "iphone", None, None)
    await app["check_watches"]()
    assert "city" not in olx_search.searches[0]
    assert "state" not in olx_search.searches[0]


def test_filters_line_only_when_set(app):
    database.save_watch(1, "диван", None, None)
    database.save_watch(1, "iphone", 20000, None, city="kharkiv", state="used", exact=True)
    text, markup = app["build_watches_list"](database.get_user_watches(1), 0)
    assert "1. iphone\n💰 до 20 000 грн · 🟢 Активна\n🔎 Харків · вживане · точний збіг" in text
    assert text.endswith("2. диван\n💰 будь-яка · 🟢 Активна")
    assert "1. 🗑 Видалити" in button_texts(markup)


def test_watch_message_lists_filters(app):
    text = app["build_watch_message"]("iphone", None, 5000, "odesa", None, False)
    assert text.startswith("Стежу за «iphone», до 5 000 грн, Одеса 🐾")
