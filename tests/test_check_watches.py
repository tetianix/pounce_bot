import threading
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

import database
from tests.helpers import make_ad, named_ad, olx_down


@pytest.fixture
def olx_ads(fake_api):
    fake_api.ads = [make_ad()]
    return fake_api.ads


@pytest.fixture
def search(fake_api, olx_ads):
    return fake_api


@pytest.fixture
def watch(search):
    database.save_watch(1, "bagllet сумка", 0, 0)


def sent_count(telegram):
    return telegram.send_photo.await_count + telegram.send_message.await_count


async def test_new_ad_notified_once(app, telegram, watch):
    await app["check_watches"]()
    await app["check_watches"]()
    assert sent_count(telegram) == 1


async def test_failed_send_does_not_repeat_new_ad(app, telegram, watch):
    error = TelegramNetworkError(method=None, message="timeout")
    telegram.send_photo.side_effect = error
    telegram.send_message.side_effect = error
    await app["check_watches"]()
    telegram.send_photo.reset_mock()
    telegram.send_message.reset_mock()
    await app["check_watches"]()
    assert sent_count(telegram) == 0


async def test_network_error_on_photo_does_not_send_text_copy(app, telegram, watch):
    telegram.send_photo.side_effect = TelegramNetworkError(method=None, message="timeout")
    await app["check_watches"]()
    telegram.send_message.assert_not_awaited()


async def test_bad_photo_falls_back_to_text(app, telegram, watch):
    telegram.send_photo.side_effect = TelegramBadRequest(method=None, message="IMAGE_PROCESS_FAILED")
    await app["check_watches"]()
    telegram.send_message.assert_awaited_once()


async def test_failed_ad_does_not_stop_other_ads(app, telegram, watch, olx_ads):
    olx_ads.append(make_ad(ad_id="937533262"))
    telegram.send_photo.side_effect = [TelegramNetworkError(method=None, message="timeout"), None]
    await app["check_watches"]()
    assert telegram.send_photo.await_count == 2


async def test_price_drop_title_and_no_max_line(app, telegram, watch, olx_ads):
    for price in (2500, 2200, 2000):
        olx_ads[:] = [make_ad(price)]
        await app["check_watches"]()
    caption = telegram.send_photo.await_args.kwargs["caption"]
    assert "📉 Подешевшало: 2 200 → 2 000 грн" in caption
    assert "💰 2 000 грн\n" in caption
    assert "було" not in caption


async def test_photo_is_prepared_outside_event_loop_thread(app, telegram, watch):
    threads = []

    def photo(url):
        threads.append(threading.current_thread())
        return "photo"

    with patch.dict(app, {"load_photo": photo}):
        await app["check_watches"]()
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()
    assert telegram.send_photo.await_args.kwargs["photo"] == "photo"


async def test_new_ad_has_no_max_line(app, telegram, watch):
    await app["check_watches"]()
    caption = telegram.send_photo.await_args_list[0].kwargs["caption"]
    assert "🆕 Нове оголошення" in caption
    assert "було" not in caption


@pytest.fixture
def wait(app):
    fake_wait = AsyncMock()
    with patch.dict(app, {"wait": fake_wait}):
        yield fake_wait


@pytest.fixture
def send(app):
    fake_send = AsyncMock()
    with patch.dict(app, {"send_ad_card": fake_send}):
        yield fake_send


def notified(send):
    return sorted((call.args[0], call.args[1]["id"]) for call in send.await_args_list)


async def test_same_watch_of_two_users_is_one_request_and_both_notified(app, watch, search, wait, send):
    database.save_watch(2, "bagllet сумка", 0, 0)
    await app["check_watches"]()
    assert len(search.searches) == 1
    assert notified(send) == [(1, "909426485"), (2, "909426485")]


async def test_two_users_both_get_price_drop(app, watch, search, wait, send, olx_ads):
    database.save_watch(2, "bagllet сумка", 0, 0)
    await app["check_watches"]()
    olx_ads[:] = [make_ad(1900)]
    send.reset_mock()
    await app["check_watches"]()
    titles = [call.args[2] for call in send.await_args_list]
    assert len(titles) == 2
    assert all("Подешевшало" in title for title in titles)


async def test_exact_and_plain_watch_share_request_but_exact_filters(app, watch, search, wait, send, olx_ads):
    database.save_watch(2, "bagllet сумка", 0, 0, exact=True)
    database.save_watch(1, "bagllet сумка", 0, 0, exact=True)
    olx_ads[:] = [named_ad("a", "Сумка Bagllet шкіряна"), named_ad("b", "Сумочка Bagllet")]
    await app["check_watches"]()
    assert len(search.searches) == 1
    assert notified(send) == [(1, "a"), (1, "b"), (2, "a")]


async def test_pause_between_requests_but_not_before_first(app, watch, search, wait, send):
    database.save_watch(1, "лампа", 0, 0)
    database.save_watch(1, "лампа", 500, 0, city="lviv")
    await app["check_watches"]()
    assert len(search.searches) == 3
    pauses = [call.args[0] for call in wait.await_args_list]
    assert len(pauses) == 2
    assert all(1 <= pause <= 2 for pause in pauses)
    assert search.searches[-1]["city"] == "lviv"


async def test_timeout_is_retried_with_growing_delay(app, watch, search, wait, send, capsys):
    search.script = [olx_down(), olx_down(), [make_ad()]]
    await app["check_watches"]()
    assert len(search.searches) == 3
    delays = [call.args[0] for call in wait.await_args_list]
    assert 2 <= delays[0] < 3 and 4 <= delays[1] < 5
    assert notified(send) == [(1, "909426485")]
    assert "повторів — 2" in capsys.readouterr().out


async def test_stops_after_failed_groups_in_row_with_one_summary_line(app, watch, search, wait, send, capsys):
    for query in ("a", "b", "c", "d", "e"):
        database.save_watch(1, query, 0, 0)
    search.on_search = lambda params: olx_down()
    await app["check_watches"]()
    log = capsys.readouterr().out
    attempts = len(app["WATCH_RETRY_DELAYS"]) + 1
    assert len(search.searches) == app["MAX_FAILED_GROUPS_IN_ROW"] * attempts
    assert log.count("\n") == 1
    assert "не вдалося — 3 (OLX не відповів: таймаут ×3)" in log
    assert "пропущено — 3" in log


async def test_one_failed_group_does_not_block_others(app, watch, search, wait, send, capsys):
    database.save_watch(2, "лампа", 0, 0)

    def fake_search(params):
        if params["q"] == "bagllet сумка":
            return olx_down("HTTP 429")
        return [named_ad("lamp", "Лампа")]

    search.on_search = fake_search
    await app["check_watches"]()
    assert notified(send) == [(2, "lamp")]
    assert "не вдалося — 1 (OLX не відповів: HTTP 429 ×1)" in capsys.readouterr().out


async def test_no_active_watches_logs_nothing(app, watch, search, wait, send, capsys):
    database.toggle_watch(1)
    await app["check_watches"]()
    assert capsys.readouterr().out == ""
    assert search.searches == []


async def test_api_down_is_counted_as_failed_group_not_crash(app, watch, search, wait, send, capsys):
    search.on_search = lambda params: httpx.ConnectError("refused")
    await app["check_watches"]()
    log = capsys.readouterr().out
    assert "не вдалося — 1 (API недоступний ×1)" in log
    send.assert_not_awaited()


async def test_watch_search_asks_api_with_group_filters(app, watch, search, wait, send):
    database.save_watch(1, "лампа", 500, 100, city="lviv", state="new")
    await app["check_watches"]()
    params = [p for p in search.searches if p["q"] == "лампа"][0]
    assert params == {"q": "лампа", "sort": "new", "period": "any", "exact": "false", "page": "1",
                      "min_price": "100", "max_price": "500", "city": "lviv", "state": "new"}


async def test_new_ad_and_its_first_price_are_saved_together(app, telegram, watch):
    await app["check_watches"]()
    assert database.ad_exists("909426485", "olx")
    assert [row["price"] for row in database.get_price_history("909426485", "olx")] == [2200]


async def test_price_is_not_saved_when_ad_save_fails(app, telegram, watch):
    with patch.dict(app, {"save_ad": MagicMock(side_effect=RuntimeError("boom"))}):
        await app["check_watches"]()
    assert not database.ad_exists("909426485", "olx")
    assert database.get_price_history("909426485", "olx") == []


async def test_one_failed_ad_does_not_stop_the_others(app, telegram, watch, olx_ads, capsys):
    olx_ads[:] = [make_ad(ad_id="1"), make_ad(ad_id="2")]
    real_save_ad = app["save_ad"]

    def flaky(ad, query, session=None):
        if ad["id"] == "1":
            raise RuntimeError("boom")
        return real_save_ad(ad, query, session)

    with patch.dict(app, {"save_ad": flaky}):
        await app["check_watches"]()
    assert not database.ad_exists("1", "olx")
    assert database.ad_exists("2", "olx")
    assert sent_count(telegram) == 1
    output = capsys.readouterr().out
    assert "olx/1" in output and "не збережено оголошень — 1" in output
