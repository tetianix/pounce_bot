from curl_cffi import requests
import re
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SORTS = {
    "new": "created_at:desc",
    "cheap": "filter_float_price:asc",
    "expensive": "filter_float_price:desc",
}

KYIV = ZoneInfo("Europe/Kyiv")

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]

DATE_RE = re.compile(r'^(.*?)(сьогодні|вчора) о (\d{1,2}):(\d{2})$', re.IGNORECASE)
RELATIVE_RE = re.compile(r'(сьогодні|вчора) о (\d{1,2}):(\d{2})', re.IGNORECASE)
FULL_DATE_RE = re.compile(r'(\d{1,2}) ([а-яіїєґʼ\']+) (\d{4})', re.IGNORECASE)

PRICE_RE = re.compile(r'(\d+(?: \d{3})*)(?:[.,](\d{1,2}))?(?!\d)')

PRICE_LABELS = [("договірна", "Договірна"), ("безкоштовно", "Безкоштовно"), ("обмін", "Обмін")]

def clean_price(text):
    text = re.sub(r'[\u00a0\u202f]', ' ', text or "").strip()
    lowered = text.lower()
    label = next((name for word, name in PRICE_LABELS if word in lowered), None)
    if "$" in text or "usd" in lowered:
        currency = "USD"
    elif "€" in text or "eur" in lowered:
        currency = "EUR"
    else:
        currency = "UAH"
    match = PRICE_RE.search(text)
    if match is None:
        return {"price": None, "currency": currency, "converted": False, "label": label}
    price = int(match.group(1).replace(" ", ""))
    converted = match.group(2) is not None and currency == "UAH"
    return {"price": price, "currency": currency, "converted": converted, "label": label}

def clean_photo(url):
    if url is None:
        return None
    photo = re.sub(r';s=\d+x\d+;q=\d+', ";s=1000x1000;q=90", url)
    return photo

def fix_date(text, now=None):
    match = DATE_RE.match(text.strip())
    if match is None:
        return text
    prefix, word, hour, minute = match.groups()
    if now is None:
        now = datetime.now(timezone.utc)
    now_utc = now.astimezone(timezone.utc)
    day = now_utc.date()
    if word.lower() == "вчора":
        day -= timedelta(days=1)
    published = datetime(day.year, day.month, day.day, int(hour), int(minute), tzinfo=timezone.utc).astimezone(KYIV)
    days_ago = (now.astimezone(KYIV).date() - published.date()).days
    time_text = published.strftime("%H:%M")
    if days_ago == 0:
        result = f"Сьогодні о {time_text}"
    elif days_ago == 1:
        result = f"Вчора о {time_text}"
    else:
        return f"{prefix}{published.day:02d} {MONTHS[published.month - 1]} {published.year} р."
    if word[0].islower():
        result = result[0].lower() + result[1:]
    return prefix + result

def parse_published_date(text, now=None):
    if not text:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    today = now.astimezone(KYIV).date()
    match = RELATIVE_RE.search(text)
    if match:
        word = match.group(1)
        return today - timedelta(days=1) if word.lower() == "вчора" else today
    match = FULL_DATE_RE.search(text)
    if match:
        day, month, year = match.groups()
        if month.lower() not in MONTHS:
            return None
        try:
            return date(int(year), MONTHS.index(month.lower()) + 1, int(day))
        except ValueError:
            return None
    return None

def scrape(query, page=1, min_price=None, max_price=None, sort="new"):
    url = f"https://www.olx.ua/uk/list/q-{query}/"

    params = {
        "page": page,
        "search[order]": SORTS[sort],
    }
    if min_price is not None:
        params["search[filter_float_price:from]"] = min_price
    if max_price is not None:
        params["search[filter_float_price:to]"] = max_price
    try:
        response = requests.get(url, params=params, timeout=10, impersonate="chrome")
    except Exception as e:
        print("помилка запиту:", e)
        return []

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        elements = soup.select('[data-cy="l-card"]')
        results = []
        for card in elements:
            price = card.select_one('[data-testid="ad-price"]')
            name = card.select_one('[data-testid="card-title-link"]')
            town = card.select_one('[data-testid="location-date"]')
            if price is None or name is None or town is None:
                continue
            parts = town.text.split(" - ", 1)
            if len(parts) != 2:
                continue
            card_id = card['id']
            photo = card.select_one('img')
            link = name['href']
            photo = clean_photo(photo.get('src')) if photo else None
            cleaned_price = clean_price(price.text)
            data = {"id": card_id,
                    "source": "olx",
                    "price": cleaned_price["price"],
                    "currency": cleaned_price["currency"],
                    "price_converted": cleaned_price["converted"],
                    "price_label": cleaned_price["label"],
                    "name" : name.text,
                    "town" : parts[0],
                    "published_date" : fix_date(parts[1]),
                    "photo" : photo,
                    "promoted": "promoted" in link,
                    "link" : f"https://www.olx.ua{link}"}
            results.append(data)
        return results
    print("статус:", response.status_code)
    return []

def scrape_details(link):
    try:
        response = requests.get(link, timeout=10, impersonate="chrome")
    except Exception:
        return {"description": None, "photos": []}
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        description = soup.select_one('[data-cy="ad_description"]')
        photo = soup.select('[data-testid="ad-photo"] img')
        photos = []
        for img in photo:
            src = img.get('src')
            if src:
                photos.append(clean_photo(src))
        text = description.get_text("\n", strip=True) if description else None
        if text and text.startswith("Опис"):
            text = text[len("Опис"):].strip()
        return {"description": text, "photos": photos}
    return {"description": None, "photos": []}

def download_photo(url):
    try:
        response = requests.get(url, timeout=10, impersonate="chrome")
    except Exception:
        return None
    if response.status_code == 200:
        return response.content
    return None
