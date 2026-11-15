from unittest.mock import patch

import database
from tests.helpers import make_ad, make_message


def hint_count(message, app):
    return [call.args[0] for call in message.answer.await_args_list].count(app["FIRST_SEARCH_HINT_TEXT"])


async def test_hint_shown_after_first_search_only(app, fake_api):
    fake_api.ads = [make_ad()]
    first = make_message()
    await app["run_search"](first, "лампа")
    assert hint_count(first, app) == 1
    second = make_message()
    await app["run_search"](second, "стіл")
    assert hint_count(second, app) == 0


async def test_hint_is_per_user(app, fake_api):
    fake_api.ads = [make_ad()]
    await app["run_search"](make_message(user_id=1), "лампа")
    other = make_message(user_id=2)
    await app["run_search"](other, "лампа")
    assert hint_count(other, app) == 1


async def test_no_hint_when_nothing_found(app, fake_api):
    fake_api.ads = []
    message = make_message()
    await app["run_search"](message, "лампа")
    assert hint_count(message, app) == 0
    assert database.mark_hint_shown(1, app["FIRST_SEARCH_HINT"]) is True


async def test_hint_comes_after_the_card(app, fake_api):
    fake_api.ads = [make_ad()]
    message = make_message()
    order = []
    message.answer_photo.side_effect = lambda **kwargs: order.append("card") or message.answer_photo.return_value
    status = message.answer.return_value
    message.answer.side_effect = lambda text, **kwargs: order.append(text) or status
    await app["run_search"](message, "лампа")
    assert order.index("card") < order.index(app["FIRST_SEARCH_HINT_TEXT"])


async def test_hint_failure_does_not_break_search(app, fake_api):
    fake_api.ads = [make_ad()]
    message = make_message()
    with patch.dict(app, {"mark_hint_shown": lambda *args: 1 / 0}):
        await app["run_search"](message, "лампа")
    message.answer_photo.assert_awaited_once()
