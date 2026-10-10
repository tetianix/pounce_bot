from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    BufferedInputFile,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from dotenv import load_dotenv
from core import search
from filters import filter_by_price
from database import (save_ad, get_link, save_watch, get_active_watches, ad_exists, get_user_watches,
                      get_watch, delete_watch, toggle_watch, get_last_price, save_price, save_favorite, get_favorites,
                      delete_favorite, get_max_price)
from scrapers.olx import scrape_details, download_photo, SORTS
import asyncio
import html
import json
import os

CHECK_INTERVAL_MINUTES = 15
CAPTION_LIMIT = 1024
MAX_STORED_RESULTS = 500
STALE_TEXT = "Це старий пошук, зроби новий 🐾"
WEBAPP_URL = "https://tetianix.github.io/pounce_webapp/"

load_dotenv()
token = os.getenv("BOT_TOKEN")
bot = Bot(token=token)
dp = Dispatcher()
message_results = {}


def save_results(message, state):
    message_results[(message.chat.id, message.message_id)] = state
    while len(message_results) > MAX_STORED_RESULTS:
        del message_results[next(iter(message_results))]


def get_results(callback):
    return message_results.get((callback.message.chat.id, callback.message.message_id))


def parse_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return int(value)


def get_ad_photo(ad):
    url = ad['photo']
    if url is None or not url.startswith('http'):
        details = scrape_details(ad['link'])
        if details["photos"]:
            url = details["photos"][0]
    return load_photo(url)


def load_photo(url):
    if url is not None and url.startswith('http'):
        data = download_photo(url)
        if data:
            return BufferedInputFile(data, filename="photo.jpg")
    return FSInputFile("placeholder.jpg")


def build_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📌 Мої пошуки"),
                KeyboardButton(text="⭐ Обране"),
            ],
            [
                KeyboardButton(text="🔍 Пошук з фільтрами", web_app=WebAppInfo(url=WEBAPP_URL)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Що шукаємо? Напр. помада",
    )


def format_price_range(min_price, max_price):
    if min_price and max_price:
        return f"{min_price}–{max_price} грн"
    if min_price:
        return f"від {min_price} грн"
    if max_price:
        return f"до {max_price} грн"
    return "будь-яка"


def build_watch_message(query, min_price, max_price):
    text = f"Стежу за «{query}»"
    if min_price or max_price:
        text += f", {format_price_range(min_price, max_price)}"
    return f"{text} 🐾\nНапишу, коли з'явиться нове або подешевшає."


def build_watch_card(watch):
    price_text = format_price_range(watch["min_price"], watch["max_price"])
    status = "Активна" if watch["is_active"] == 1 else "На паузі"
    button_text = "⏸ Пауза" if watch["is_active"] == 1 else "▶️ Увімкнути"
    text = f"🔍 {watch['query']}\nЦіна: {price_text}\n{status}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=button_text, callback_data=f"pause:{watch['id']}"),
        InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete:{watch['id']}")
    ]])
    return text, keyboard


def format_price_text(ad):
    price_text = f"{ad['price']} грн" if ad['price'] is not None else "Ціна не вказана"
    max_price = get_max_price(ad['id'], ad['source'])
    if ad['price'] is not None and max_price is not None and max_price > ad['price']:
        price_text += f"  📉 було {max_price}"
    return price_text


def format_ad_text(ad):
    name = html.escape(ad['name'])
    town = html.escape(ad['town'] or "")
    date = html.escape(ad['published_date'] or "")
    return f"<b>{name}</b>\n💰 {format_price_text(ad)}\n📍 {town}\n🕒 <i>{date}</i>"


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def build_info_caption(ad, description):
    name = ad['name']
    town = ad['town'] or ""
    price_text = format_price_text(ad)
    header = f"<b>{html.escape(name)}</b>\n💰 {price_text}\n📍 {html.escape(town)}\n\n"
    if not description:
        return header + "Продавець не додав опис"
    available = CAPTION_LIMIT - utf16_len(f"{name}\n💰 {price_text}\n📍 {town}\n\n")
    if utf16_len(description) > available:
        description = description[:available - 1]
        while utf16_len(description) > available - 1:
            description = description[:-1]
        description = description.rstrip() + "…"
    return header + f"<blockquote expandable>{html.escape(description)}</blockquote>"


def build_ad_card(ad, index, total, mode="search", watching=False):
    text = format_ad_text(ad)
    if mode == "fav":
        action_button = InlineKeyboardButton(text="🗑 Прибрати", callback_data=f"favdel:{index}")
    else:
        action_button = InlineKeyboardButton(text="⭐ В обране", callback_data=f"fav:{ad['source']}:{ad['id']}")
    rows = [
        [
            InlineKeyboardButton(text="◀️", callback_data=f"nav:{index - 1}"),
            InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"nav:{index + 1}"),
        ],
        [
            InlineKeyboardButton(text="Детальніше", callback_data=f"info:{index}"),
            action_button,
        ],
    ]
    if mode == "search":
        if watching:
            rows.append([InlineKeyboardButton(text="✅ Стежу", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(text="🔔 Стежити", callback_data="watch")])
    rows.append([InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link'])])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def build_info_keyboard(ad, index, photo_index, photo_count):
    rows = []
    if photo_count > 1:
        rows.append([
            InlineKeyboardButton(text="◀", callback_data=f"photo:{photo_index - 1}"),
            InlineKeyboardButton(text=f"Фото {photo_index + 1} / {photo_count}", callback_data="noop"),
            InlineKeyboardButton(text="▶", callback_data=f"photo:{photo_index + 1}"),
        ])
    rows.append([InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link'])])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav:{index}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def replace_button(markup, callback_data, new_button):
    rows = []
    for row in markup.inline_keyboard:
        rows.append([new_button if button.callback_data == callback_data else button for button in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def track_price(ad):
    if ad["price"] is None:
        return None
    last_price = get_last_price(ad["id"], ad["source"])
    if last_price is None:
        save_price(ad["id"], ad["source"], ad["price"])
        return None
    if last_price != ad["price"]:
        save_price(ad["id"], ad["source"], ad["price"])
        return last_price
    return None

async def send_ad_card(chat_id, ad, prefix="", query=None):
    lines = []
    if prefix:
        lines.append(f"<b>{prefix}</b>")
    if query:
        lines.append(f"🔍 за пошуком «{html.escape(query)}»")
    lines.append(format_ad_text(ad))
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Детальніше", callback_data=f"details:{ad['source']}:{ad['id']}"),
            InlineKeyboardButton(text="⭐ В обране", callback_data=f"fav:{ad['source']}:{ad['id']}"),
        ],
        [
            InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link']),
        ],
    ])
    try:
        await bot.send_photo(chat_id=chat_id, photo=get_ad_photo(ad), caption=text,
                             reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def run_search(message, query, min_price=None, max_price=None, sort="new", watching=False):
    status = await message.answer("Шукаю...")
    try:
        ads = search(query, min_price=min_price, max_price=max_price, sort=sort)
        if max_price is not None or min_price is not None:
            ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
        ads.sort(key=lambda ad: ad["promoted"])
        if not ads:
            if min_price is not None or max_price is not None:
                await message.answer("Нічого не знайдено 😿\nСпробуй розширити діапазон цін або змінити запит")
            else:
                await message.answer("Нічого не знайдено 😿\nСпробуй коротший запит або інші слова")
            return
        for ad in ads:
            save_ad(ad, query)
            track_price(ad)
        text, keyboard = build_ad_card(ads[0], 0, len(ads), watching=watching)
        card = await message.answer_photo(photo=get_ad_photo(ads[0]), caption=text, reply_markup=keyboard,
                                          parse_mode="HTML")
        save_results(card, {
            "ads": ads,
            "mode": "search",
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
            "watching": watching,
        })
    finally:
        await status.delete()


async def check_watches():
    watches = get_active_watches()
    for watch in watches:
        user_id = watch["user_id"]
        query = watch["query"]
        max_price = watch["max_price"]
        min_price = watch["min_price"]
        max_price = None if max_price == 0 else max_price
        min_price = None if min_price == 0 else min_price
        ads = search(query, min_price=min_price, max_price=max_price)
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
        for ad in ads:
            if not ad_exists(ad["id"], ad["source"]):
                await send_ad_card(user_id, ad, "🆕 Нове оголошення", query)
            old_price = track_price(ad)
            if old_price is not None:
                prefix = "📉 Подешевшало" if ad["price"] < old_price else "📈 Подорожчало"
                await send_ad_card(user_id, ad, f"{prefix} було {old_price} грн", query)
            save_ad(ad, query)


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Мяу! Я Pounce 🐾\n"
        "Полюю на оголошення OLX, поки ти займаєшся своїми справами.\n\n"
        "🔎 Напиши, що шукаєш, наприклад <i>помада Dior</i>\n"
        "🎯 Або відкрий «Пошук з фільтрами», щоб задати ціну\n"
        "🔔 Натисни «Стежити», і я напишу, коли з'явиться нове або подешевшає",
        reply_markup=build_main_keyboard(),
        parse_mode="HTML",
    )


@dp.message(F.text == "📌 Мої пошуки")
async def watches_handler(message: Message):
    watches = get_user_watches(message.from_user.id)
    if not watches:
        await message.answer("Наразі пошуків немає")
        return
    for watch in watches:
        text, keyboard = build_watch_card(watch)
        await message.answer(text, reply_markup=keyboard)


@dp.message(F.text == "⭐ Обране")
async def saved_handler(message: Message):
    ads = list(get_favorites(message.from_user.id))
    if not ads:
        await message.answer("Обране порожнє")
        return
    text, keyboard = build_ad_card(ads[0], 0, len(ads), "fav")
    card = await message.answer_photo(photo=get_ad_photo(ads[0]), caption=text, reply_markup=keyboard,
                                      parse_mode="HTML")
    save_results(card, {"ads": ads, "mode": "fav"})


@dp.callback_query(F.data.startswith("nav:"))
async def nav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    index = int(parts[1])
    state = get_results(callback)
    if state is None:
        await callback.answer(STALE_TEXT)
        return
    ads = state["ads"]
    if index < 0 or index >= len(ads):
        await callback.answer("Це край списку")
        return
    ad = ads[index]
    text, keyboard = build_ad_card(ad, index, len(ads), state["mode"], state.get("watching", False))
    await callback.message.edit_media(
        media=InputMediaPhoto(media=get_ad_photo(ad), caption=text, parse_mode="HTML"),
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("info:"))
async def info_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    index = int(parts[1])
    state = get_results(callback)
    if state is None or index >= len(state["ads"]):
        await callback.answer(STALE_TEXT)
        return
    ad = state["ads"][index]

    details = scrape_details(ad['link'])
    text = build_info_caption(ad, details["description"])
    state["details"] = {
        "index": index,
        "photos": details["photos"],
        "caption": text,
    }
    keyboard = build_info_keyboard(ad, index, 0, len(details["photos"]))
    await callback.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("photo:"))
async def photo_handler(callback: CallbackQuery):
    photo_index = int(callback.data.split(":")[1])
    state = get_results(callback)
    details = state.get("details") if state else None
    if details is None:
        await callback.answer(STALE_TEXT)
        return
    photos = details["photos"]
    if photo_index < 0 or photo_index >= len(photos):
        await callback.answer("Це край списку")
        return
    ad = state["ads"][details["index"]]
    keyboard = build_info_keyboard(ad, details["index"], photo_index, len(photos))
    await callback.message.edit_media(
        media=InputMediaPhoto(media=load_photo(photos[photo_index]), caption=details["caption"], parse_mode="HTML"),
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("details:"))
async def details_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    ads_id = parts[2]
    link = get_link(ads_id, source)
    if link is None:
        await callback.answer("Опис не знайдено")
        return
    details = scrape_details(link)
    media = []
    for url in details["photos"]:
        media.append(InputMediaPhoto(media=url))
    if len(media) > 1:
        await callback.message.answer_media_group(media)
    elif len(media) == 1:
        await callback.message.answer_photo(details["photos"][0])
    description = details["description"] or "Опис відсутній"
    await callback.message.answer(description[:3000])
    await callback.answer()


@dp.callback_query(F.data.startswith("fav:"))
async def fav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    ad_id = parts[2]
    save_favorite(callback.from_user.id, ad_id, source)
    new_button = InlineKeyboardButton(text="✅ В обраному", callback_data="noop")
    await callback.message.edit_reply_markup(
        reply_markup=replace_button(callback.message.reply_markup, callback.data, new_button)
    )
    await callback.answer("⭐ Збережено")


@dp.callback_query(F.data == "watch")
async def watch_button_handler(callback: CallbackQuery):
    state = get_results(callback)
    if state is None or state["mode"] != "search":
        await callback.answer(STALE_TEXT)
        return
    save_watch(callback.from_user.id, state["query"], state["max_price"], state["min_price"])
    state["watching"] = True
    new_button = InlineKeyboardButton(text="✅ Стежу", callback_data="noop")
    await callback.message.edit_reply_markup(
        reply_markup=replace_button(callback.message.reply_markup, "watch", new_button)
    )
    await callback.message.answer(build_watch_message(state["query"], state["min_price"], state["max_price"]))
    await callback.answer()


@dp.callback_query(F.data.startswith("favdel:"))
async def favdel_handler(callback: CallbackQuery):
    index = int(callback.data.split(":")[1])
    state = get_results(callback)
    if state is None or state["mode"] != "fav" or index >= len(state["ads"]):
        await callback.answer(STALE_TEXT)
        return
    ads = state["ads"]
    ad = ads.pop(index)
    delete_favorite(callback.from_user.id, ad["id"], ad["source"])

    if not ads:
        message_results.pop((callback.message.chat.id, callback.message.message_id), None)
        await callback.message.delete()
        await callback.message.answer("Обране порожнє")
        await callback.answer("Прибрано")
        return

    index = min(index, len(ads) - 1)
    text, keyboard = build_ad_card(ads[index], index, len(ads), "fav")
    await callback.message.edit_media(
        media=InputMediaPhoto(media=get_ad_photo(ads[index]), caption=text, parse_mode="HTML"),
        reply_markup=keyboard
    )
    await callback.answer("Прибрано з обраного")


@dp.callback_query(F.data.startswith("unfav:"))
async def unfav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    ad_id = parts[2]
    delete_favorite(callback.from_user.id, ad_id, source)
    await callback.message.delete()
    await callback.answer("Прибрано з обраного")


@dp.callback_query(F.data.startswith("delete:"))
async def delete_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    watch_id = int(parts[1])
    delete_watch(watch_id)
    await callback.message.delete()
    await callback.answer("Видалено")


@dp.callback_query(F.data.startswith("pause:"))
async def pause_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    watch_id = int(parts[1])
    toggle_watch(watch_id)
    watch = get_watch(watch_id)
    text, keyboard = build_watch_card(watch)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@dp.message(F.web_app_data)
async def webapp_handler(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        await message.answer("Не вдалося прочитати фільтри")
        return

    query = data.get("query")
    query = query.strip() if isinstance(query, str) else ""
    if not query:
        await message.answer("Напиши, що шукати 🐾")
        return

    min_price = parse_price(data.get("min_price"))
    max_price = parse_price(data.get("max_price"))
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    sort = data.get("sort")
    if not isinstance(sort, str) or sort not in SORTS:
        sort = "new"

    watching = data.get("watch") is True
    if watching:
        save_watch(message.from_user.id, query, max_price, min_price)

    await run_search(message, query, min_price, max_price, sort, watching)

    if watching:
        await message.answer(build_watch_message(query, min_price, max_price))


@dp.message(F.text)
async def text_handler(message: Message):
    if message.text.startswith("/"):
        await message.answer("Не знаю такої команди 🐾")
        return
    await run_search(message, message.text.strip())


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_watches, "interval", minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    await bot.delete_my_commands()
    await dp.start_polling(bot)


asyncio.run(main())