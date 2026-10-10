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
)
from dotenv import load_dotenv
from core import search
from filters import filter_by_price
from database import (save_ad, get_link, save_watch, get_active_watches, ad_exists, get_user_watches,
                      get_watch, delete_watch, toggle_watch, get_last_price, save_price, save_favorite, get_favorites,
                      delete_favorite, get_max_price)
from scrapers.olx import scrape_details, download_photo
import asyncio
import html
import os

CHECK_INTERVAL_MINUTES = 15

load_dotenv()
token = os.getenv("BOT_TOKEN")
bot = Bot(token=token)
dp = Dispatcher()
user_results = {}


def parse_query(text):
    words = text.split(" ")
    results = []
    max_price = None
    min_price = None
    for word in words:
        if word.startswith("<"):
            max_price = int(word[1:])
        elif word.startswith(">"):
            min_price = int(word[1:])
        else:
            results.append(word)
    query = " ".join(results)
    return query, max_price, min_price


def get_ad_photo(ad):
    url = ad['photo']
    if url is None or not url.startswith('http'):
        details = scrape_details(ad['link'])
        if details["photos"]:
            url = details["photos"][0]

    if url is not None and url.startswith('http'):
        data = download_photo(url)
        if data:
            return BufferedInputFile(data, filename="photo.jpg")

    return FSInputFile("placeholder.jpg")


def build_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📌 Мої пошуки"),
            KeyboardButton(text="⭐ Обране"),
        ]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Що шукаємо? Напр. помада <500",
    )


def build_watch_card(watch):
    price_text = ""
    if watch["max_price"] > 0:
        price_text = f"до {watch['max_price']} грн"
    if watch["min_price"] > 0:
        price_text += f" від {watch['min_price']} грн"
    price_text = price_text if price_text else "будь-яка"
    status = "Активна" if watch["is_active"] == 1 else "На паузі"
    button_text = "⏸ Пауза" if watch["is_active"] == 1 else "▶️ Увімкнути"
    text = f"🔍 {watch['query']}\nЦіна: {price_text}\n{status}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=button_text, callback_data=f"pause:{watch['id']}"),
        InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete:{watch['id']}")
    ]])
    return text, keyboard


def format_ad_text(ad):
    name = html.escape(ad['name'])
    town = html.escape(ad['town'] or "")
    date = html.escape(ad['published_date'] or "")
    price_text = f"{ad['price']} грн" if ad['price'] is not None else "Ціна не вказана"
    max_price = get_max_price(ad['id'], ad['source'])
    if ad['price'] is not None and max_price is not None and max_price > ad['price']:
        price_text += f"  📉 було {max_price}"
    return f"<b>{name}</b>\n💰 {price_text}\n📍 {town}\n🕒 <i>{date}</i>"


def build_ad_card(ad, index, total, mode="search"):
    text = format_ad_text(ad)
    if mode == "fav":
        action_button = InlineKeyboardButton(text="🗑 Прибрати", callback_data=f"favdel:{index}")
    else:
        action_button = InlineKeyboardButton(text="⭐ В обране", callback_data=f"fav:{ad['source']}:{ad['id']}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="◀️", callback_data=f"nav:{index - 1}"),
            InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"nav:{index + 1}"),
        ],
        [
            InlineKeyboardButton(text="Детальніше", callback_data=f"info:{index}"),
            action_button,
        ],
        [
            InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link']),
        ],
    ])
    return text, keyboard

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

async def send_ad_card(chat_id, ad, prefix=""):
    text = f"<b>{prefix}</b>\n{format_ad_text(ad)}" if prefix else format_ad_text(ad)
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


async def run_search(message, text):
    query, max_price, min_price = parse_query(text)
    await message.answer("Шукаю...")
    ads = search(query)
    if max_price is not None or min_price is not None:
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
    ads.sort(key=lambda ad: ad["promoted"])
    if not ads:
        await message.answer("Нічого не знайдено")
        return
    for ad in ads:
        save_ad(ad, query)
        track_price(ad)
    user_results[message.from_user.id] = {"ads": ads, "mode": "search"}
    text, keyboard = build_ad_card(ads[0], 0, len(ads))
    await message.answer_photo(photo=get_ad_photo(ads[0]), caption=text, reply_markup=keyboard, parse_mode="HTML")


async def check_watches():
    watches = get_active_watches()
    for watch in watches:
        user_id = watch["user_id"]
        query = watch["query"]
        max_price = watch["max_price"]
        min_price = watch["min_price"]
        ads = search(query)
        max_price = None if max_price == 0 else max_price
        min_price = None if min_price == 0 else min_price
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
        for ad in ads:
            if not ad_exists(ad["id"], ad["source"]):
                await send_ad_card(user_id, ad, "🆕 Нове оголошення")
            old_price = track_price(ad)
            if old_price is not None:
                prefix = "📉 Подешевшало" if ad["price"] < old_price else "📈 Подорожчало"
                await send_ad_card(user_id, ad, f"{prefix} було {old_price} грн")
            save_ad(ad, query)


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привіт! Я Pounce 🐾\nНапиши, що шукаєш — і я покажу оголошення.",
        reply_markup=build_main_keyboard()
    )


@dp.message(Command("search"))
async def search_handler(message: Message):
    parts = message.text.split(" ", 1)
    if len(parts) != 2:
        await message.answer("Напиши що шукати: /search товар")
        return
    await run_search(message, parts[1])


@dp.message(Command("watch"))
async def watch_handler(message: Message):
    parts = message.text.split(" ", 1)
    if len(parts) != 2:
        await message.answer("Напиши що відстежувати: /watch товар")
        return
    query, max_price, min_price = parse_query(parts[1])
    save_watch(message.from_user.id, query, max_price, min_price)
    await message.answer(f"Стежу за «{query}»")


@dp.message(Command("watches"))
@dp.message(F.text == "📌 Мої пошуки")
async def watches_handler(message: Message):
    watches = get_user_watches(message.from_user.id)
    if not watches:
        await message.answer("Наразі пошуків немає")
        return
    for watch in watches:
        text, keyboard = build_watch_card(watch)
        await message.answer(text, reply_markup=keyboard)


@dp.message(Command("saved"))
@dp.message(F.text == "⭐ Обране")
async def saved_handler(message: Message):
    ads = list(get_favorites(message.from_user.id))
    if not ads:
        await message.answer("Обране порожнє")
        return
    user_results[message.from_user.id] = {"ads": ads, "mode": "fav"}
    text, keyboard = build_ad_card(ads[0], 0, len(ads), "fav")
    await message.answer_photo(photo=get_ad_photo(ads[0]), caption=text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data.startswith("nav:"))
async def nav_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    index = int(parts[1])
    state = user_results.get(callback.from_user.id)
    if state is None:
        await callback.answer("Пошук застарів, зроби новий")
        return
    ads = state["ads"]
    if index < 0 or index >= len(ads):
        await callback.answer("Це край списку")
        return
    ad = ads[index]
    text, keyboard = build_ad_card(ad, index, len(ads), state["mode"])
    await callback.message.edit_media(
        media=InputMediaPhoto(media=get_ad_photo(ad), caption=text, parse_mode="HTML"),
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("info:"))
async def info_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    index = int(parts[1])
    state = user_results.get(callback.from_user.id)
    if state is None or index >= len(state["ads"]):
        await callback.answer("Пошук застарів, зроби новий")
        return
    ad = state["ads"][index]

    details = scrape_details(ad['link'])
    description = details["description"] or "Опис відсутній"

    text = f"{ad['name']}\n{ad['price']} грн\n\n{description}"
    if len(text) > 1024:
        text = text[:1020] + "..."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Відкрити на OLX", url=ad['link'])],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"nav:{index}")],
    ])
    await callback.message.edit_caption(caption=text, reply_markup=keyboard)
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

    new_rows = []
    for row in callback.message.reply_markup.inline_keyboard:
        new_row = []
        for button in row:
            if button.callback_data == callback.data:
                button = InlineKeyboardButton(text="✅ В обраному", callback_data="noop")
            new_row.append(button)
        new_rows.append(new_row)
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows))

    await callback.answer("⭐ Збережено")


@dp.callback_query(F.data.startswith("favdel:"))
async def favdel_handler(callback: CallbackQuery):
    index = int(callback.data.split(":")[1])
    state = user_results.get(callback.from_user.id)
    if state is None or state["mode"] != "fav" or index >= len(state["ads"]):
        await callback.answer("Список застарів, відкрий обране знову")
        return
    ads = state["ads"]
    ad = ads.pop(index)
    delete_favorite(callback.from_user.id, ad["id"], ad["source"])

    if not ads:
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


@dp.message(F.text)
async def text_handler(message: Message):
    if message.text.startswith("/"):
        await message.answer("Не знаю такої команди 🐾")
        return
    await run_search(message, message.text)


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_watches, "interval", minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    await dp.start_polling(bot)


asyncio.run(main())