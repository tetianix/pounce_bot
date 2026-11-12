import threading
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import make_callback, make_message, named_ad


@pytest.fixture
def threads():
    return []


@pytest.fixture
def spy(threads):
    def make(result):
        def call(*args, **kwargs):
            threads.append(threading.current_thread())
            return result(*args) if callable(result) else result

        return call

    return make


def assert_off_main_thread(threads):
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()


def label(name):
    return lambda value: f"{name}:{value['id'] if isinstance(value, dict) else value}"


@pytest.fixture
def photo_spies(app, spy):
    with patch.dict(app, {"get_ad_photo": spy(label("ad")), "load_photo": spy(label("url"))}):
        yield


def edited_photo(callback):
    return callback.message.edit_media.await_args.kwargs["media"].media


@pytest.mark.usefixtures("photo_spies")
async def test_first_search_card(app, threads):
    message = make_message()
    with patch.dict(app, {"search": MagicMock(return_value=[named_ad("a", "Лампа")])}):
        await app["run_search"](message, "лампа")
    assert_off_main_thread(threads)
    assert message.answer_photo.await_args.kwargs["photo"] == "ad:a"


@pytest.mark.usefixtures("photo_spies")
async def test_favorites_card(app, threads):
    message = make_message()
    with patch.dict(app, {"get_favorites": lambda user_id: [named_ad("f", "Лампа")]}):
        await app["saved_handler"](message)
    assert_off_main_thread(threads)
    assert message.answer_photo.await_args.kwargs["photo"] == "ad:f"


@pytest.mark.usefixtures("photo_spies")
async def test_carousel_navigation(app, threads):
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "search"}
    callback = make_callback(data="nav:1")
    await app["nav_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == "ad:b"


@pytest.mark.usefixtures("photo_spies")
async def test_details_gallery(app, threads):
    app["message_results"][(1, 10)] = {
        "ads": [named_ad("a", "A")], "mode": "search",
        "details": {"index": 0, "photos": ["https://x/1.jpg", "https://x/2.jpg"], "caption": "опис"},
    }
    callback = make_callback(data="photo:1")
    await app["photo_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == "url:https://x/2.jpg"


@pytest.mark.usefixtures("photo_spies")
async def test_card_after_removing_from_favorites(app, threads):
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "fav"}
    callback = make_callback(data="favdel:0")
    await app["favdel_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == "ad:b"


NO_DETAILS = {"description": "Опис лампи", "photos": [], "price": None}


@pytest.fixture
def photo_stub(app):
    with patch.dict(app, {"get_ad_photo": MagicMock(return_value="photo")}):
        yield


@pytest.mark.usefixtures("photo_stub")
async def test_search_runs_in_worker_thread(app, spy, threads):
    message = make_message()
    with patch.dict(app, {"search": spy([named_ad("a", "Лампа")])}):
        await app["run_search"](message, "лампа")
    assert_off_main_thread(threads)
    message.answer_photo.assert_awaited_once()


@pytest.mark.usefixtures("photo_stub")
async def test_search_for_period_runs_in_worker_thread(app, spy, threads):
    message = make_message()
    with patch.dict(app, {"search_recent": spy([named_ad("a", "Лампа")])}):
        await app["run_search"](message, "лампа", period="3d")
    assert_off_main_thread(threads)
    message.answer_photo.assert_awaited_once()


@pytest.mark.usefixtures("photo_stub")
async def test_carousel_details_run_in_worker_thread(app, spy, threads):
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "Лампа")], "mode": "search"}
    callback = make_callback(data="info:0")
    with patch.dict(app, {"scrape_details": spy(NO_DETAILS)}):
        await app["info_handler"](callback)
    assert_off_main_thread(threads)
    assert "Опис лампи" in callback.message.edit_caption.await_args.kwargs["caption"]


@pytest.mark.usefixtures("photo_stub")
async def test_notification_details_run_in_worker_thread(app, spy, threads):
    callback = make_callback(data="details:olx:a")
    with patch.dict(app, {"scrape_details": spy(NO_DETAILS),
                          "get_link": lambda ad_id, source: "https://www.olx.ua/d/a.html"}):
        await app["details_handler"](callback)
    assert_off_main_thread(threads)
    assert callback.message.answer.await_args.args[0] == "Опис лампи"
