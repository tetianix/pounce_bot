import threading
from unittest.mock import patch

import pytest

from tests.helpers import make_ad, make_callback, make_message, named_ad

COVER = "https://x/cover.jpg"


@pytest.fixture
def threads():
    return []


@pytest.fixture
def photo_spy(app, fake_api, threads):
    def load(url):
        threads.append(threading.current_thread())
        return f"url:{url}"

    with patch.dict(app, {"load_photo": load}):
        yield


def assert_off_main_thread(threads):
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()


def edited_photo(callback):
    return callback.message.edit_media.await_args.kwargs["media"].media


@pytest.mark.usefixtures("photo_spy")
async def test_first_search_card(app, fake_api, threads):
    fake_api.ads = [named_ad("a", "Лампа")]
    message = make_message()
    await app["run_search"](message, "лампа")
    assert_off_main_thread(threads)
    assert message.answer_photo.await_args.kwargs["photo"] == f"url:{COVER}"
    assert fake_api.detail_requests == ["/ads/olx/a"]


@pytest.mark.usefixtures("photo_spy")
async def test_favorites_card(app, threads):
    message = make_message()
    with patch.dict(app, {"get_favorites": lambda user_id: [named_ad("f", "Лампа")]}):
        await app["saved_handler"](message)
    assert_off_main_thread(threads)
    assert message.answer_photo.await_args.kwargs["photo"] == f"url:{COVER}"


@pytest.mark.usefixtures("photo_spy")
async def test_carousel_navigation(app, threads):
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "search"}
    callback = make_callback(data="nav:1")
    await app["nav_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == f"url:{COVER}"


@pytest.mark.usefixtures("photo_spy")
async def test_details_gallery(app, threads):
    app["message_results"][(1, 10)] = {
        "ads": [named_ad("a", "A")], "mode": "search",
        "details": {"index": 0, "photos": ["https://x/1.jpg", "https://x/2.jpg"], "caption": "опис"},
    }
    callback = make_callback(data="photo:1")
    await app["photo_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == "url:https://x/2.jpg"


@pytest.mark.usefixtures("photo_spy")
async def test_card_after_removing_from_favorites(app, threads):
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "A"), named_ad("b", "B")], "mode": "fav"}
    callback = make_callback(data="favdel:0")
    await app["favdel_handler"](callback)
    assert_off_main_thread(threads)
    assert edited_photo(callback) == f"url:{COVER}"


@pytest.mark.usefixtures("photo_spy")
async def test_ad_with_photo_does_not_ask_api(app, fake_api, threads):
    ad = {**make_ad(), "photo": "https://x/own.jpg"}
    assert await app["fetch_ad_photo"](ad) == "url:https://x/own.jpg"
    assert fake_api.requests == []


async def test_api_down_gives_placeholder_not_crash(app, fake_api):
    fake_api.down = True
    seen = []
    with patch.dict(app, {"load_photo": lambda url: seen.append(url) or "placeholder"}):
        assert await app["fetch_ad_photo"](make_ad()) == "placeholder"
    assert seen == [None]
