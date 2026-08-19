from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from dotenv import load_dotenv
from core import search
from filters import filter_by_price
from database import (save_ad, get_link, get_ads_by_query, save_watch, get_active_watches, ad_exists, get_user_watches,
                      get_watch, delete_watch, toggle_watch)
from scrapers.olx import scrape_details
import asyncio
import os

CHECK_INTERVAL_MINUTES = 1

load_dotenv()
token = os.getenv("BOT_TOKEN")
bot = Bot(token=token)
dp = Dispatcher()

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


async def send_ad_card(chat_id, ad, prefix=""):
    photo = ad['photo']
    if photo is None or not photo.startswith("http"):
        details = scrape_details(ad['link'])
        if details["photos"]:
            photo = details["photos"][0]
    text = f"{prefix}{ad['name']}\n{ad['price']} грн\n{ad['town']}\n{ad['link']}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Детальніше", callback_data=f"details:{ad['source']}:{ad['id']}")]])
    if photo is not None and photo.startswith("http"):
        try:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, reply_markup=keyboard)
        except Exception:
            await asyncio.sleep(1)
            try:
                await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, reply_markup=keyboard)
            except Exception:
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

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
                await send_ad_card(user_id, ad, "🆕 Нове оголошення\n")
            save_ad(ad, query)


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Привіт! Я Pounce 🐾")

@dp.message(Command("search"))
async def search_handler(message: Message):
    parts = message.text.split(" ", 1)
    if len(parts) != 2:
        await message.answer("Напиши що шукати: /search товар")
        return
    query, max_price, min_price = parse_query(parts[1])
    await message.answer("Шукаю...")
    ads = search(query)
    total_found = len(ads)
    if max_price is not None or min_price is not None:
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
    for ad in ads[:5]:
        save_ad(ad, query)
        await send_ad_card(message.chat.id, ad)
    max_str = max_price if max_price is not None else 0
    min_str = min_price if min_price is not None else 0
    if total_found >= 40:
        more_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ще 5", callback_data=f"more:{query}:2:{max_str}:{min_str}")]])
        await message.answer("Показати більше?", reply_markup=more_keyboard)

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
async def watches_handler(message: Message):
    watches = get_user_watches(message.from_user.id)
    if not watches:
        await message.answer("Наразі пошуків немає")
        return
    for watch in watches:
        text, keyboard = build_watch_card(watch)
        await message.answer(text, reply_markup=keyboard)

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

@dp.callback_query(F.data.startswith("more:"))
async def more_handler(callback: CallbackQuery):
    parts = callback.data.split(":")
    query = parts[1]
    page = int(parts[2])
    max_price = int(parts[3])
    min_price = int(parts[4])
    max_price = None if max_price == 0 else max_price
    min_price = None if min_price == 0 else min_price
    ads = search(query, page)
    total_found = len(ads)
    if max_price is not None or min_price is not None:
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
    if not ads:
        await callback.answer("Більше немає")
        return
    for ad in ads[:5]:
        save_ad(ad, query)
        await send_ad_card(callback.message.chat.id, ad)
    max_str = max_price if max_price is not None else 0
    min_str = min_price if min_price is not None else 0
    if total_found >= 40:
        more_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ще 5", callback_data=f"more:{query}:{page + 1}:{max_str}:{min_str}")]])
        await callback.message.answer("Показати більше?", reply_markup=more_keyboard)
    await callback.answer()

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_watches, "interval", minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    await dp.start_polling(bot)
asyncio.run(main())