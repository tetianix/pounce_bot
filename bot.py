from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
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
import db
from api_client import ApiClient, ApiError, EMPTY_DETAILS, OlxUnavailable, DEFAULT_API_URL, make_client
from core import PERIODS
from filters import has_all_words
from database import (save_ad, save_watch, get_active_watches, ad_exists, get_user_watches,
                      get_watch, delete_watch, toggle_watch, get_last_price, save_price, save_favorite, get_favorites,
                      delete_favorite, get_max_price, is_favorite, delete_user_watch)
from scrapers.olx import download_photo, format_published_date, SORTS, CITIES, STATES
from collections import Counter
import asyncio
import html
import json
import os
import random
from time import monotonic

CHECK_INTERVAL_MINUTES = 15
WATCH_PAUSE_SECONDS = (1, 2)
WATCH_RETRY_DELAYS = (2, 4)
MAX_FAILED_GROUPS_IN_ROW = 3
CAPTION_LIMIT = 1024
MAX_STORED_RESULTS = 200
MAX_RESULTS_PER_CHAT = 10
RESULTS_TTL_SECONDS = 3600
STALE_TEXT = "Це старий пошук, зроби новий 🐾"
OLX_DOWN_TEXT = "OLX зараз не відповідає 😿\nСпробуй за хвилину"
API_DOWN_TEXT = "Сервіс пошуку зараз недоступний 😿\nСпробуй за хвилину"
NO_WATCHES_TEXT = "Наразі пошуків немає"
WATCHES_PER_PAGE = 5
CONVERTED_PRICE_THRESHOLD = 0.03
CURRENCY_SIGNS = {"UAH": "грн", "USD": "$", "EUR": "€"}
WEBAPP_URL = "https://tetianix.github.io/pounce_webapp/"

load_dotenv()
token = os.getenv("BOT_TOKEN")
bot = Bot(token=token)
dp = Dispatcher()
api = ApiClient(make_client(os.getenv("API_URL") or DEFAULT_API_URL))
message_results = {}


def drop_expired_results(now):
    while message_results:
        key = next(iter(message_results))
        if now - message_results[key].get("used_at", now) < RESULTS_TTL_SECONDS:
            break
        del message_results[key]


def save_results(message, state):
    now = monotonic()
    drop_expired_results(now)
    state["used_at"] = now
    chat_id = message.chat.id
    message_results[(chat_id, message.message_id)] = state
    chat_keys = [key for key in message_results if key[0] == chat_id]
    for key in chat_keys[:-MAX_RESULTS_PER_CHAT]:
        del message_results[key]
    while len(message_results) > MAX_STORED_RESULTS:
        del message_results[next(iter(message_results))]


def get_results(callback):
    now = monotonic()
    drop_expired_results(now)
    key = (callback.message.chat.id, callback.message.message_id)
    state = message_results.pop(key, None)
    if state is None:
        return None
    if now - state.get("used_at", now) >= RESULTS_TTL_SECONDS:
        return None
    state["used_at"] = now
    message_results[key] = state
    return state


def parse_price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return int(value)


def load_photo(url):
    if url is not None and url.startswith('http'):
        data = download_photo(url)
        if data:
            return BufferedInputFile(data, filename="photo.jpg")
    return FSInputFile("placeholder.jpg")


async def fetch_ad_photo(ad):
    url = ad['photo']
    if url is None or not url.startswith('http'):
        try:
            details = await api.details(ad['source'], ad['id'])
        except ApiError:
            details = None
        if details and details["photos"]:
            url = details["photos"][0]
    return await fetch_photo(url)


async def fetch_photo(url):
    return await asyncio.to_thread(load_photo, url)


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
        return f"{format_number(min_price)}–{format_money(max_price, 'UAH')}"
    if min_price:
        return f"від {format_money(min_price, 'UAH')}"
    if max_price:
        return f"до {format_money(max_price, 'UAH')}"
    return "будь-яка"


def describe_filters(city=None, state=None, exact=False):
    parts = []
    if city in CITIES:
        parts.append(CITIES[city]["name"])
    if state in STATES:
        parts.append(STATES[state].lower())
    if exact:
        parts.append("точний збіг")
    return parts


def build_watch_message(query, min_price, max_price, city=None, state=None, exact=False):
    text = f"Стежу за «{query}»"
    if min_price or max_price:
        text += f", {format_price_range(min_price, max_price)}"
    for part in describe_filters(city, state, exact):
        text += f", {part}"
    return f"{text} 🐾\nНапишу, коли з'явиться нове або подешевшає."


def count_pages(total):
    return max(1, -(-total // WATCHES_PER_PAGE))


def build_watches_list(watches, page):
    if not watches:
        return NO_WATCHES_TEXT, None
    pages = count_pages(len(watches))
    page = min(max(page, 0), pages - 1)
    start = page * WATCHES_PER_PAGE
    lines = [f"📌 Мої пошуки · {len(watches)}"]
    rows = []
    for number, watch in enumerate(watches[start:start + WATCHES_PER_PAGE], start + 1):
        active = watch["is_active"] == 1
        price_text = format_price_range(watch["min_price"], watch["max_price"])
        status = "🟢 Активна" if active else "⏸ На паузі"
        lines.append(f"\n{number}. {watch['query']}\n💰 {price_text} · {status}")
        filters = describe_filters(watch["city"], watch["state"], watch["exact"])
        if filters:
            lines.append("🔎 " + " · ".join(filters))
        rows.append([
            InlineKeyboardButton(text=f"{number}. {'⏸ Пауза' if active else '▶️ Увімкнути'}",
                                 callback_data=f"pause:{watch['id']}:{page}"),
            InlineKeyboardButton(text=f"{number}. 🗑 Видалити", callback_data=f"delete:{watch['id']}:{page}"),
        ])
    if pages > 1:
        rows.append([
            InlineKeyboardButton(text="◀️", callback_data=f"wpage:{page - 1}"),
            InlineKeyboardButton(text=f"{page + 1} / {pages}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"wpage:{page + 1}"),
        ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def format_number(value):
    return f"{value:,}".replace(",", " ")


def format_money(value, currency, converted=False):
    text = format_number(value) + " " + CURRENCY_SIGNS.get(currency, "грн")
    return "≈ " + text if converted else text


def is_real_change(old_price, new_price, converted):
    if not converted:
        return old_price != new_price
    return abs(new_price - old_price) > old_price * CONVERTED_PRICE_THRESHOLD


def format_price_change(old_price, new_price, currency, converted=False):
    prefix = "📉 Подешевшало" if new_price < old_price else "📈 Подорожчало"
    text = f"{format_number(old_price)} → {format_money(new_price, currency)}"
    return f"{prefix}: " + ("≈ " + text if converted else text)


def format_price_text(ad, show_max=True):
    if ad['price'] is None:
        return ad['price_label'] or "Ціна не вказана"
    converted = bool(ad['price_converted'])
    price_text = format_money(ad['price'], ad['currency'], converted)
    if ad['price_label']:
        price_text += f" · {ad['price_label']}"
    if not show_max:
        return price_text
    max_price = get_max_price(ad['id'], ad['source'], ad['currency'])
    if max_price is not None and max_price > ad['price'] and is_real_change(max_price, ad['price'], converted):
        price_text += f"  📉 було {format_money(max_price, ad['currency'], converted)}"
    return price_text


def format_details_price(ad, original):
    if original is None or original["price"] is None or not ad['price_converted']:
        return format_price_text(ad)
    text = format_money(original["price"], original["currency"])
    if ad['price_label']:
        text += f" · {ad['price_label']}"
    return text + f" ({format_money(ad['price'], ad['currency'], True)})"


def format_ad_text(ad, show_max=True):
    name = html.escape(ad['name'])
    town = html.escape(ad['town'] or "")
    date = html.escape(format_published_date(ad['published_date']) or "")
    return f"<b>{name}</b>\n💰 {format_price_text(ad, show_max)}\n📍 {town}\n🕒 <i>{date}</i>"


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def build_info_caption(ad, description, original_price=None):
    name = ad['name']
    town = ad['town'] or ""
    price_text = format_details_price(ad, original_price)
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


def build_fav_button(ad, is_fav):
    if is_fav:
        return InlineKeyboardButton(text="✅ В обраному", callback_data=f"unfav:{ad['source']}:{ad['id']}")
    return InlineKeyboardButton(text="⭐ В обране", callback_data=f"fav:{ad['source']}:{ad['id']}")


def build_ad_card(ad, index, total, mode="search", watching=False, user_id=None):
    text = format_ad_text(ad)
    if mode == "fav":
        action_button = InlineKeyboardButton(text="🗑 Прибрати", callback_data=f"favdel:{index}")
    else:
        is_fav = user_id is not None and is_favorite(user_id, ad['id'], ad['source'])
        action_button = build_fav_button(ad, is_fav)
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
            rows.append([InlineKeyboardButton(text="✅ Стежу", callback_data="unwatch")])
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

def track_price(ad, session=None):
    if ad["price"] is None:
        return None
    last_price = get_last_price(ad["id"], ad["source"], ad["currency"], session)
    if last_price is None:
        save_price(ad["id"], ad["source"], ad["price"], ad["currency"], session)
        return None
    if is_real_change(last_price, ad["price"], ad["price_converted"]):
        save_price(ad["id"], ad["source"], ad["price"], ad["currency"], session)
        return last_price
    return None


def store_ad(ad, query):
    with db.Session.begin() as session:
        save_ad(ad, query, session)
        return track_price(ad, session)

async def send_ad_card(chat_id, ad, prefix="", query=None):
    lines = []
    if prefix:
        lines.append(f"<b>{prefix}</b>")
    if query:
        lines.append(f"🔍 за пошуком «{html.escape(query)}»")
    lines.append(format_ad_text(ad, show_max=False))
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Детальніше", callback_data=f"details:{ad['source']}:{ad['id']}"),
            build_fav_button(ad, is_favorite(chat_id, ad['id'], ad['source'])),
        ],
        [
            InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link']),
        ],
    ])
    photo = await fetch_ad_photo(ad)
    try:
        await bot.send_photo(chat_id=chat_id, photo=photo, caption=text,
                             reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def run_search(message, query, min_price=None, max_price=None, sort="new", watching=False, period="any",
                     city=None, state=None, exact=False):
    status = await message.answer("Шукаю...")
    try:
        try:
            ads = await api.search(query, min_price=min_price, max_price=max_price, sort=sort, period=period,
                                   city=city, state=state, exact=exact)
        except OlxUnavailable as e:
            print("пошук: OLX не відповів:", e)
            await message.answer(OLX_DOWN_TEXT)
            return
        except ApiError as e:
            print("пошук: API недоступний:", e)
            await message.answer(API_DOWN_TEXT)
            return
        if not ads:
            if describe_filters(city, state, exact):
                await message.answer("Нічого не знайдено 😿\nСпробуй прибрати частину фільтрів або змінити запит")
            elif min_price is not None or max_price is not None:
                await message.answer("Нічого не знайдено 😿\nСпробуй розширити діапазон цін або змінити запит")
            else:
                await message.answer("Нічого не знайдено 😿\nСпробуй коротший запит або інші слова")
            return
        for ad in ads:
            store_ad(ad, query)
        text, keyboard = build_ad_card(ads[0], 0, len(ads), watching=watching,
                                       user_id=message.from_user.id)
        card = await message.answer_photo(photo=await fetch_ad_photo(ads[0]), caption=text, reply_markup=keyboard,
                                          parse_mode="HTML")
        save_results(card, {
            "ads": ads,
            "mode": "search",
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
            "city": city,
            "state": state,
            "exact": exact,
            "watching": watching,
        })
    finally:
        await status.delete()


async def wait(seconds):
    await asyncio.sleep(seconds)


def group_watches(watches):
    groups = {}
    for watch in watches:
        key = (watch["query"], watch["min_price"] or None, watch["max_price"] or None,
               watch["city"] or None, watch["state"] or None)
        groups.setdefault(key, []).append(watch)
    return groups


async def search_for_watches(key, stats):
    query, min_price, max_price, city, state = key
    for delay in WATCH_RETRY_DELAYS + (None,):
        try:
            return await api.search(query, min_price=min_price, max_price=max_price, city=city, state=state)
        except ApiError:
            if delay is None:
                raise
            stats["retries"] += 1
            await wait(delay + random.uniform(0, 1))


def watch_users(group, ad, query):
    users = []
    for watch in group:
        if watch["exact"] and not has_all_words(ad["name"], query):
            continue
        if watch["user_id"] not in users:
            users.append(watch["user_id"])
    return users


async def notify_watchers(group, query, ads, stats):
    for ad in ads:
        try:
            is_new = not ad_exists(ad["id"], ad["source"])
            old_price = store_ad(ad, query)
        except Exception as e:
            stats["save_errors"] += 1
            print(f"стеження: не вдалося зберегти оголошення {ad['source']}/{ad['id']}: {type(e).__name__}: {e}")
            continue
        if not is_new and old_price is None:
            continue
        for user_id in watch_users(group, ad, query):
            try:
                if is_new:
                    await send_ad_card(user_id, ad, "🆕 Нове оголошення", query)
                    stats["sent"] += 1
                if old_price is not None:
                    title = format_price_change(old_price, ad["price"], ad["currency"], ad["price_converted"])
                    await send_ad_card(user_id, ad, title, query)
                    stats["sent"] += 1
            except Exception as e:
                stats["send_errors"] += 1
                stats["last_send_error"] = f"{type(e).__name__}: {e}"


def format_check_summary(watch_count, stats, errors, seconds):
    parts = [f"стежень — {watch_count}", f"запитів до OLX — {stats['requests']}", f"повторів — {stats['retries']}"]
    if errors:
        details = ", ".join(f"{error} ×{count}" for error, count in errors.items())
        parts.append(f"не вдалося — {sum(errors.values())} ({details})")
    if stats["skipped"]:
        parts.append(f"пропущено — {stats['skipped']}, бо OLX не відповідає")
    if stats["save_errors"]:
        parts.append(f"не збережено оголошень — {stats['save_errors']}")
    parts.append(f"сповіщень — {stats['sent']}")
    send_errors = f"помилок надсилання — {stats['send_errors']}"
    if stats["send_errors"]:
        send_errors += f" (остання: {stats['last_send_error']})"
    parts.append(send_errors)
    parts.append(f"{seconds:.0f} с")
    return "перевірка стежень: " + ", ".join(parts)


async def check_watches():
    started = monotonic()
    watches = get_active_watches()
    if not watches:
        return
    groups = group_watches(watches)
    stats = Counter()
    errors = Counter()
    failed_in_row = 0
    for number, (key, group) in enumerate(groups.items()):
        if number:
            await wait(random.uniform(*WATCH_PAUSE_SECONDS))
        stats["requests"] += 1
        try:
            ads = await search_for_watches(key, stats)
        except ApiError as e:
            errors[str(e)] += 1
            failed_in_row += 1
            if failed_in_row >= MAX_FAILED_GROUPS_IN_ROW:
                stats["skipped"] = len(groups) - number - 1
                break
            continue
        failed_in_row = 0
        await notify_watchers(group, key[0], ads, stats)
    print(format_check_summary(len(watches), stats, errors, monotonic() - started))


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
    text, keyboard = build_watches_list(get_user_watches(message.from_user.id), 0)
    await message.answer(text, reply_markup=keyboard)


@dp.message(F.text == "⭐ Обране")
async def saved_handler(message: Message):
    ads = list(get_favorites(message.from_user.id))
    if not ads:
        await message.answer("Обране порожнє")
        return
    text, keyboard = build_ad_card(ads[0], 0, len(ads), "fav")
    card = await message.answer_photo(photo=await fetch_ad_photo(ads[0]), caption=text, reply_markup=keyboard,
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
    text, keyboard = build_ad_card(ad, index, len(ads), state["mode"], state.get("watching", False),
                                   callback.from_user.id)
    await callback.message.edit_media(
        media=InputMediaPhoto(media=await fetch_ad_photo(ad), caption=text, parse_mode="HTML"),
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

    try:
        details = await api.details(ad['source'], ad['id']) or EMPTY_DETAILS
    except ApiError as e:
        print("деталі: API недоступний:", e)
        await callback.answer(API_DOWN_TEXT, show_alert=True)
        return
    text = build_info_caption(ad, details["description"], details["price"])
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
        media=InputMediaPhoto(media=await fetch_photo(photos[photo_index]), caption=details["caption"],
                              parse_mode="HTML"),
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
    try:
        details = await api.details(source, ads_id)
    except ApiError as e:
        print("деталі: API недоступний:", e)
        await callback.answer(API_DOWN_TEXT, show_alert=True)
        return
    if details is None:
        await callback.answer("Опис не знайдено")
        return
    media = []
    for url in details["photos"]:
        media.append(InputMediaPhoto(media=url))
    if len(media) > 1:
        await callback.message.answer_media_group(media)
    elif len(media) == 1:
        await callback.message.answer_photo(details["photos"][0])
    description = details["description"] or "Опис відсутній"
    original = details["price"]
    if original and original["price"] is not None and original["currency"] != "UAH":
        description = f"💰 {format_money(original['price'], original['currency'])}\n\n{description}"
    await callback.message.answer(description[:3000])
    await callback.answer()


@dp.callback_query(F.data.startswith("fav:"))
async def fav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    ad_id = parts[2]
    save_favorite(callback.from_user.id, ad_id, source)
    new_button = build_fav_button({"source": source, "id": ad_id}, True)
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
    save_watch(callback.from_user.id, state["query"], state["max_price"], state["min_price"],
               state.get("city"), state.get("state"), state.get("exact", False))
    state["watching"] = True
    new_button = InlineKeyboardButton(text="✅ Стежу", callback_data="unwatch")
    await callback.message.edit_reply_markup(
        reply_markup=replace_button(callback.message.reply_markup, "watch", new_button)
    )
    await callback.message.answer(build_watch_message(state["query"], state["min_price"], state["max_price"],
                                                      state.get("city"), state.get("state"),
                                                      state.get("exact", False)))
    await callback.answer()


@dp.callback_query(F.data == "unwatch")
async def unwatch_button_handler(callback: CallbackQuery):
    state = get_results(callback)
    if state is None or state["mode"] != "search":
        await callback.answer(STALE_TEXT)
        return
    delete_user_watch(callback.from_user.id, state["query"], state["max_price"], state["min_price"],
                      state.get("city"), state.get("state"), state.get("exact", False))
    state["watching"] = False
    new_button = InlineKeyboardButton(text="🔔 Стежити", callback_data="watch")
    await callback.message.edit_reply_markup(
        reply_markup=replace_button(callback.message.reply_markup, "unwatch", new_button)
    )
    await callback.message.answer(f"Більше не стежу за «{state['query']}»")
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
        media=InputMediaPhoto(media=await fetch_ad_photo(ads[index]), caption=text, parse_mode="HTML"),
        reply_markup=keyboard
    )
    await callback.answer("Прибрано з обраного")


@dp.callback_query(F.data.startswith("unfav:"))
async def unfav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    source = parts[1]
    ad_id = parts[2]
    delete_favorite(callback.from_user.id, ad_id, source)
    new_button = build_fav_button({"source": source, "id": ad_id}, False)
    await callback.message.edit_reply_markup(
        reply_markup=replace_button(callback.message.reply_markup, callback.data, new_button)
    )
    await callback.answer("Прибрано з обраного")


async def show_watches_page(callback, page):
    text, keyboard = build_watches_list(get_user_watches(callback.from_user.id), page)
    await callback.message.edit_text(text, reply_markup=keyboard)


def get_own_watch(callback):
    parts = callback.data.split(":")
    if len(parts) != 3:
        return None, 0
    watch = get_watch(int(parts[1]))
    if watch is None or watch["user_id"] != callback.from_user.id:
        return None, 0
    return watch, int(parts[2])


@dp.callback_query(F.data.startswith("wpage:"))
async def watches_page_handler(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    if page < 0 or page >= count_pages(len(get_user_watches(callback.from_user.id))):
        await callback.answer("Це край списку")
        return
    await show_watches_page(callback, page)
    await callback.answer()


@dp.callback_query(F.data.startswith("delete:"))
async def delete_handler(callback: CallbackQuery):
    watch, page = get_own_watch(callback)
    if watch is None:
        await callback.answer(STALE_TEXT)
        return
    delete_watch(watch["id"])
    await show_watches_page(callback, page)
    await callback.answer(f"Видалено «{watch['query']}»")


@dp.callback_query(F.data.startswith("pause:"))
async def pause_handler(callback: CallbackQuery):
    watch, page = get_own_watch(callback)
    if watch is None:
        await callback.answer(STALE_TEXT)
        return
    toggle_watch(watch["id"])
    await show_watches_page(callback, page)
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
    period = data.get("period", "any")
    if not isinstance(period, str) or period not in PERIODS:
        period = "any"
    city = data.get("city")
    if not isinstance(city, str) or city not in CITIES:
        city = None
    state = data.get("state")
    if not isinstance(state, str) or state not in STATES:
        state = None
    exact = data.get("exact") is True

    watching = data.get("watch") is True
    if watching:
        save_watch(message.from_user.id, query, max_price, min_price, city, state, exact)

    await run_search(message, query, min_price, max_price, sort, watching, period, city, state, exact)

    if watching:
        await message.answer(build_watch_message(query, min_price, max_price, city, state, exact))


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
    try:
        await dp.start_polling(bot)
    finally:
        await api.client.aclose()


asyncio.run(main())