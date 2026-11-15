from unittest.mock import AsyncMock, MagicMock

from tests.helpers import button_texts, make_callback


def make_text_message():
    message = MagicMock()
    message.answer = AsyncMock()
    return message


def test_main_keyboard_has_help_on_third_row(app):
    keyboard = app["build_main_keyboard"]()
    assert [button.text for button in keyboard.keyboard[2]] == ["❓ Допомога"]


def test_guide_has_four_pages(app):
    assert len(app["GUIDE_PAGES"]) == 4


def test_guide_page_buttons_and_wraparound(app):
    _, markup = app["build_guide_page"](0)
    assert button_texts(markup) == ["◀", "1/4", "▶", "✕ Закрити"]
    assert markup.inline_keyboard[0][0].callback_data == "guide:3"
    assert markup.inline_keyboard[0][2].callback_data == "guide:1"
    _, markup = app["build_guide_page"](3)
    assert markup.inline_keyboard[0][2].callback_data == "guide:0"


def test_every_callback_fits_telegram_limit(app):
    for page in range(len(app["GUIDE_PAGES"])):
        _, markup = app["build_guide_page"](page)
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64


async def test_start_has_help_button_and_menu(app):
    message = make_text_message()
    await app["start_handler"](message)
    first, second = message.answer.await_args_list
    assert button_texts(first.kwargs["reply_markup"]) == ["❓ Як користуватись"]
    assert "❓ Допомога" in [b.text for row in second.kwargs["reply_markup"].keyboard for b in row]


async def test_help_button_opens_first_page(app):
    message = make_text_message()
    await app["help_handler"](message)
    text, markup = message.answer.await_args.args[0], message.answer.await_args.kwargs["reply_markup"]
    assert text == app["GUIDE_PAGES"][0]
    assert "1/4" in button_texts(markup)


async def test_guide_button_edits_same_message(app):
    callback = make_callback(data="guide:2")
    await app["guide_handler"](callback)
    args = callback.message.edit_text.await_args
    assert args.args[0] == app["GUIDE_PAGES"][2]
    assert "3/4" in button_texts(args.kwargs["reply_markup"])
    callback.answer.assert_awaited_once()


async def test_guide_ignores_unknown_page(app):
    callback = make_callback(data="guide:9")
    await app["guide_handler"](callback)
    callback.message.edit_text.assert_not_awaited()


async def test_guide_close_deletes_message(app):
    callback = make_callback(data="guide_close")
    callback.message.delete = AsyncMock()
    await app["guide_close_handler"](callback)
    callback.message.delete.assert_awaited_once()
