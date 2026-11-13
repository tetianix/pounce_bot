import httpx
import pytest

from api_client import ApiClient, ApiUnavailable, OlxUnavailable
from tests.helpers import make_ad, make_callback, make_message, named_ad, olx_down

DETAILS = {"description": "Опис лампи", "photos": ["https://x/1.jpg"],
           "price": {"price": 500, "currency": "USD", "converted": False, "label": None}}


def client_for(handler):
    return ApiClient(httpx.AsyncClient(base_url="http://api.test", transport=httpx.MockTransport(handler)))


async def test_search_params_travel_as_query_string(app, fake_api):
    fake_api.ads = [make_ad()]
    await app["run_search"](make_message(), "iphone 13", min_price=100, max_price=900, sort="cheap", period="3d",
                            city="lviv", state="used", exact=True)
    assert fake_api.searches == [{"q": "iphone 13", "sort": "cheap", "period": "3d", "exact": "true", "page": "1",
                                  "min_price": "100", "max_price": "900", "city": "lviv", "state": "used"}]


async def test_ads_from_api_become_carousel(app, fake_api):
    fake_api.ads = [named_ad("a", "Лампа"), named_ad("b", "Стіл")]
    message = make_message()
    await app["run_search"](message, "лампа")
    assert [ad["id"] for ad in app["message_results"][(1, 10)]["ads"]] == ["a", "b"]
    assert "Лампа" in message.answer_photo.await_args.kwargs["caption"]


async def test_api_down_tells_user_and_does_not_crash(app, fake_api):
    fake_api.down = True
    message = make_message()
    await app["run_search"](message, "лампа")
    texts = [call.args[0] for call in message.answer.await_args_list]
    assert texts[-1] == app["API_DOWN_TEXT"]
    message.answer_photo.assert_not_awaited()
    message.answer.return_value.delete.assert_awaited()


async def test_api_internal_error_is_also_api_down(app, fake_api):
    fake_api.script = [httpx.Response(500, text="boom")]
    message = make_message()
    await app["run_search"](message, "лампа")
    assert message.answer.await_args_list[-1].args[0] == app["API_DOWN_TEXT"]


async def test_olx_down_has_its_own_text(app, fake_api):
    fake_api.script = [olx_down()]
    message = make_message()
    await app["run_search"](message, "лампа")
    assert message.answer.await_args_list[-1].args[0] == app["OLX_DOWN_TEXT"]


async def test_carousel_details_from_api(app, fake_api):
    fake_api.details = DETAILS
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "Лампа")], "mode": "search"}
    callback = make_callback(data="info:0")
    await app["info_handler"](callback)
    assert fake_api.detail_requests == ["/ads/olx/a"]
    assert "Опис лампи" in callback.message.edit_caption.await_args.kwargs["caption"]
    assert app["message_results"][(1, 10)]["details"]["photos"] == ["https://x/1.jpg"]


async def test_carousel_details_api_down_shows_alert(app, fake_api):
    fake_api.down = True
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "Лампа")], "mode": "search"}
    callback = make_callback(data="info:0")
    await app["info_handler"](callback)
    callback.answer.assert_awaited_once_with(app["API_DOWN_TEXT"], show_alert=True)
    callback.message.edit_caption.assert_not_awaited()


async def test_carousel_details_of_unknown_ad_show_empty_description(app, fake_api):
    fake_api.known_ads = False
    app["message_results"][(1, 10)] = {"ads": [named_ad("a", "Лампа")], "mode": "search"}
    callback = make_callback(data="info:0")
    await app["info_handler"](callback)
    callback.message.edit_caption.assert_awaited_once()


async def test_notification_details_from_api(app, fake_api):
    fake_api.details = {**DETAILS, "photos": []}
    callback = make_callback(data="details:olx:a")
    await app["details_handler"](callback)
    assert fake_api.detail_requests == ["/ads/olx/a"]
    assert callback.message.answer.await_args.args[0].endswith("Опис лампи")
    assert callback.message.answer.await_args.args[0].startswith("💰 500 $")


async def test_notification_details_unknown_ad(app, fake_api):
    fake_api.known_ads = False
    callback = make_callback(data="details:olx:a")
    await app["details_handler"](callback)
    callback.answer.assert_awaited_once_with("Опис не знайдено")


async def test_notification_details_api_down_shows_alert(app, fake_api):
    fake_api.down = True
    callback = make_callback(data="details:olx:a")
    await app["details_handler"](callback)
    callback.answer.assert_awaited_once_with(app["API_DOWN_TEXT"], show_alert=True)
    callback.message.answer.assert_not_awaited()


async def test_timeout_is_api_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ApiUnavailable, match="вчасно"):
        await client_for(handler).search("лампа")


async def test_502_without_json_is_still_olx_unavailable():
    with pytest.raises(OlxUnavailable, match="OLX не відповів"):
        await client_for(lambda request: httpx.Response(502, text="bad gateway")).search("лампа")


async def test_422_is_api_unavailable_not_empty_result():
    with pytest.raises(ApiUnavailable, match="422"):
        await client_for(lambda request: httpx.Response(422, json={"detail": []})).search("лампа")


async def test_search_omits_empty_filters():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"count": 0, "cached": False, "ads": []})

    assert await client_for(handler).search("лампа") == []
    assert seen == [{"q": "лампа", "sort": "new", "period": "any", "exact": "false", "page": "1"}]


@pytest.mark.parametrize("name", ["search", "search_recent", "scrape", "scrape_details", "OlxError"])
def test_bot_does_not_use_scraper_directly(app, name):
    assert name not in app
