import httpx
import json
from unittest.mock import AsyncMock, MagicMock


def make_ad(price=2200, ad_id="909426485", name="Сумка Bagllet"):
    return {"id": ad_id, "source": "olx", "name": name, "price": price,
            "currency": "UAH", "price_converted": False, "price_label": None, "town": "Київ",
            "published_date": "11 жовтня 2026 р.", "photo": None, "promoted": False,
            "link": "https://www.olx.ua/d/obyavlenie/sumka-bagllet-ID110gp8.html"}


def named_ad(ad_id, name):
    return make_ad(ad_id=ad_id, name=name)


def make_callback(markup=None, user_id=1, data=""):
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = user_id
    callback.message.chat.id = user_id
    callback.message.message_id = 10
    callback.message.reply_markup = markup
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_media = AsyncMock()
    callback.message.edit_caption = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def make_message(data=None, user_id=1):
    message = MagicMock()
    message.from_user.id = user_id
    message.chat.id = user_id
    message.web_app_data.data = json.dumps(data)
    message.answer = AsyncMock()
    card = MagicMock()
    card.chat.id = user_id
    card.message_id = 10
    message.answer_photo = AsyncMock(return_value=card)
    return message


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class FakeApi:
    def __init__(self):
        self.ads = []
        self.details = {"description": "Опис", "photos": ["https://x/cover.jpg"], "price": None}
        self.known_ads = True
        self.down = False
        self.script = []
        self.on_search = None
        self.requests = []

    @property
    def searches(self):
        return [dict(request.url.params) for request in self.requests if request.url.path == "/search"]

    @property
    def detail_requests(self):
        return [request.url.path for request in self.requests if request.url.path.startswith("/ads/")]

    def handle(self, request):
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("refused")
        if request.url.path == "/search":
            return self.answer_search(dict(request.url.params))
        if not self.known_ads:
            return httpx.Response(404, json={"detail": "Оголошення не знайдено"})
        return httpx.Response(200, json=self.details)

    def answer_search(self, params):
        step = self.script.pop(0) if self.script else self.on_search(params) if self.on_search else self.ads
        if isinstance(step, Exception):
            raise step
        if isinstance(step, httpx.Response):
            return step
        return httpx.Response(200, json={"count": len(step), "cached": False, "ads": step})


def olx_down(reason="таймаут"):
    return httpx.Response(502, json={"detail": f"OLX не відповів: {reason}"})
