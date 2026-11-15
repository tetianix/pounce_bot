# Pounce 🐾

![tests](https://github.com/tetianix/pounce_bot/actions/workflows/tests.yml/badge.svg)

A Telegram bot that monitors OLX.ua listings for you: search, filter, track new ads and price drops, and keep favorites.

## Що вміє бот

- 🔎 **Пошук на OLX** — напиши, що шукаєш, і гортай оголошення в каруселі.
- 🎯 **Фільтри в Mini App** — ціна, місто, стан товару, сортування, період і точний збіг у назві.
- 🔔 **Стеження** — бот сам перевіряє OLX кожні 15 хвилин.
- 📉 **Сповіщення** про нові оголошення та зниження ціни, **історія цін** кожного оголошення.
- ⭐ **Обране** і «Детальніше» з описом та галереєю фото.
- ❓ **Гайд для нових користувачів** — покрокова інструкція просто в чаті.

<table>
  <tr>
    <td align="center"><img src="docs/start.png" width="250" alt="Старт"><br><sub>Старт</sub></td>
    <td align="center"><img src="docs/guide.png" width="250" alt="Гайд"><br><sub>Гайд для нових користувачів</sub></td>
    <td align="center"><img src="docs/carousel.png" width="250" alt="Пошук"><br><sub>Пошук і карусель</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/details.png" width="250" alt="Детальніше"><br><sub>Детальніше: опис і фото</sub></td>
    <td align="center"><img src="docs/miniapp.png" width="250" alt="Mini App"><br><sub>Mini App з фільтрами</sub></td>
    <td align="center"><img src="docs/watches.png" width="250" alt="Мої пошуки"><br><sub>Мої пошуки (стеження)</sub></td>
  </tr>
</table>

## Архітектура

```mermaid
flowchart LR
    User([Користувач]) <--> TG[Telegram]
    TG <--> Bot["Бот<br/>aiogram 3 + APScheduler"]
    WebApp["Mini App<br/>GitHub Pages"] -. "форма пошуку (sendData)" .-> TG
    Bot -- "httpx" --> API["FastAPI-сервіс<br/>кеш + ліміт запитів"]
    API -- "curl_cffi + BeautifulSoup" --> OLX[(OLX.ua)]
    Bot --> DB[(PostgreSQL)]
```

Бот ніколи не ходить на OLX сам: увесь скрапінг ізольований у окремому FastAPI-сервісі, який тримає кеш пошуку й обмежує кількість паралельних запитів, а бот спілкується з ним через `httpx`. Стеження, обране та історія цін лежать у PostgreSQL (для локального запуску достатньо SQLite), схема керується міграціями Alembic. Mini App — статична сторінка на GitHub Pages: форма фільтрів повертає боту JSON через `sendData`.

## Стек

- **Python 3**, **aiogram 3** — Telegram-бот
- **FastAPI** — API-сервіс, **httpx** — клієнт для бота
- **curl_cffi**, **BeautifulSoup** — скрапінг OLX
- **SQLAlchemy 2.0** (+ Alembic) — база даних
- Також: APScheduler (періодичні перевірки), pytest (тести й покриття, CI на GitHub Actions)
