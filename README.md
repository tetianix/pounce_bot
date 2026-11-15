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

## Цікаві технічні рішення

- **Час OLX → Київ.** У видачі OLX час приходить у UTC («Сьогодні о 08:56»); `fix_date()` переводить його в `Europe/Kyiv`, і межі періоду теж рахуються за київським календарем.
- **Ціни й валюти.** У пошуку OLX віддає все в гривнях (валютні оголошення перераховані, з копійками), а оригінал (`500 $`) є лише на сторінці оголошення — тому його показуємо тільки в «Детальніше». Історію цін порівнюємо лише в однаковій валюті, а для перерахованих цін зміною вважається лише більша за 3%, щоб курс не давав фальшивих «Подешевшало».
- **Фільтр періоду.** OLX такого фільтра не має, тож бот гортає сторінки «нових» оголошень і відсікає старі за київськими днями; якщо OLX збоїть на сторінці після першої, віддається вже знайдене.
- **Стан каруселі — на повідомлення, а не на користувача.** Дві відкриті каруселі не псують одна одну; стан живе годину від останнього використання, а ліміти на чат і загальний не дають пам'яті рости.
- **SQLite → PostgreSQL.** Схемою керують моделі SQLAlchemy й міграції Alembic, адреса бази береться з `DATABASE_URL`. Для переїзду є скрипт, що переносить дані однією транзакцією й друкує кількість рядків у обох базах, щоб їх можна було звірити.
- **Семафор і кеш в API.** Єдине місце, що ходить на OLX, — FastAPI-сервіс: не більше двох одночасних запитів (`asyncio.Semaphore`) і кеш пошуку на 3 хвилини. Тому API працює з одним worker — кеш і ліміт живуть у пам'яті процесу.
- **Помилка OLX ≠ «нічого не знайдено».** Скрапер кидає виняток при таймауті чи не-200, API віддає 502, а бот показує окремі тексти для «OLX не відповів» і «сервіс недоступний».
- **Ізоляція помилок у перевірці стежень.** Стеження групуються за (запит, ціни, місто, стан) — один запит на групу; між групами пауза, невдалі запити повторюються, оголошення, яке не вдалося зберегти, пропускається, а цикл не падає. Після кількох невдалих груп поспіль він зупиняється, а в лог іде один підсумковий рядок.
- **Одноразові підказки.** Таблиця `shown_hints` (користувач + назва підказки) пам'ятає, що підказку вже показано, тому підказка про «Стежити» після першого пошуку приходить лише раз.

## Структура проєкту

```
bot.py                  хендлери, клавіатури, карусель, стеження (APScheduler)
api_client.py           httpx-клієнт бота до API
core.py                 пошук по джерелах, пошук за період
filters.py              цінові фільтри, точний збіг
db.py, models.py        підключення до бази, моделі SQLAlchemy
database.py             функції доступу до бази
api/                    FastAPI-сервіс (єдиний, що ходить на OLX)
  main.py               ендпоінти /health, /search, /ads/...
  service.py            скрапер, семафор, кеш пошуку
scrapers/olx.py         скрапінг OLX (curl_cffi + BeautifulSoup)
alembic/                міграції бази
scripts/                бекап бази, перенесення SQLite → PostgreSQL
deploy/                 systemd-юніт API
tests/                  pytest-тести
docs/                   скріншоти для README
```

## Запуск локально

```bash
git clone https://github.com/tetianix/pounce_bot.git
cd pounce_bot
python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
```

У `.env` потрібен лише `BOT_TOKEN` (токен від [@BotFather](https://t.me/BotFather)). `DATABASE_URL` без значення — це SQLite `database.db`, для PostgreSQL вкажи, наприклад, `postgresql://user:password@localhost/pounce`. `API_URL` за замовчуванням `http://127.0.0.1:8000`.

```bash
.venv/bin/alembic upgrade head
```

Бот не створює таблиці сам, їх створюють міграції. Далі в двох терміналах:

```bash
.venv/bin/python -m uvicorn api.main:app --port 8000
.venv/bin/python bot.py
```

Документація API — `http://127.0.0.1:8000/docs`.

## Тести

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Звіт покриття друкується автоматично; у CI (GitHub Actions) поріг покриття — 80%. Мережа в тестах заблокована, база — SQLite in-memory, OLX і Telegram підмінені моками.

## Деплой

Бот і API працюють на Oracle Cloud як два systemd-сервіси: `pounce-api` (uvicorn лише на `127.0.0.1:8000`, один worker) і `pounce` (бот). Оновлення завжди в такому порядку:

```
git pull → pip install -r requirements.txt → scripts/backup_db.py → alembic upgrade head
→ systemctl restart pounce-api → curl /health → systemctl restart pounce
```

API перезапускається раніше за бота, бекап робиться до міграцій, а щодня о 4:00 його запускає cron.

## Плани

- 🤖 AI-аналіз оголошень.
- 🐳 Docker Compose для запуску бота, API і бази однією командою.
