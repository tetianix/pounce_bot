from curl_cffi import requests
import functools
import re
import threading
from bs4 import BeautifulSoup, SoupStrainer
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SORTS = {
    "new": "created_at:desc",
    "cheap": "filter_float_price:asc",
    "expensive": "filter_float_price:desc",
}

CITIES = {
    "kyiv": {"slug": "kiev", "name": "Київ"},
    "kharkiv": {"slug": "kharkov", "name": "Харків"},
    "odesa": {"slug": "odessa", "name": "Одеса"},
    "dnipro": {"slug": "dnepr", "name": "Дніпро"},
    "lviv": {"slug": "lvov", "name": "Львів"},
    "zaporizhzhia": {"slug": "zaporozhe", "name": "Запоріжжя"},
    "vinnytsia": {"slug": "vinnitsa", "name": "Вінниця"},
    "zhytomyr": {"slug": "zhitomir", "name": "Житомир"},
    "ivano-frankivsk": {"slug": "ivano-frankovsk", "name": "Івано-Франківськ"},
    "kropyvnytskyi": {"slug": "kropivnitskiy", "name": "Кропивницький"},
    "lutsk": {"slug": "lutsk", "name": "Луцьк"},
    "mykolaiv": {"slug": "nikolaev", "name": "Миколаїв"},
    "poltava": {"slug": "poltava", "name": "Полтава"},
    "rivne": {"slug": "rovno", "name": "Рівне"},
    "sumy": {"slug": "sumy", "name": "Суми"},
    "ternopil": {"slug": "ternopol", "name": "Тернопіль"},
    "uzhhorod": {"slug": "uzhgorod", "name": "Ужгород"},
    "kherson": {"slug": "kherson", "name": "Херсон"},
    "khmelnytskyi": {"slug": "khmelnitskiy", "name": "Хмельницький"},
    "cherkasy": {"slug": "cherkassy", "name": "Черкаси"},
    "chernivtsi": {"slug": "chernovtsy", "name": "Чернівці"},
    "chernihiv": {"slug": "chernigov", "name": "Чернігів"},
}

STATES = {
    "new": "Нове",
    "used": "Вживане",
}

KYIV = ZoneInfo("Europe/Kyiv")

class OlxError(Exception):
    pass

OLX_LOCK = threading.Lock()

def one_request_at_a_time(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with OLX_LOCK:
            return func(*args, **kwargs)
    return wrapper

LISTING_ONLY = SoupStrainer(attrs={"data-testid": "listing-grid"})

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]

DATE_RE = re.compile(r'^(.*?)(сьогодні|вчора) о (\d{1,2}):(\d{2})$', re.IGNORECASE)
RELATIVE_RE = re.compile(r'(сьогодні|вчора) о (\d{1,2}):(\d{2})', re.IGNORECASE)
FULL_DATE_RE = re.compile(r'(\d{1,2}) ([а-яіїєґʼ\']+) (\d{4})', re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r'^\s*р\.')
RELATIVE_DAYS = ["Сьогодні", "Вчора", "Позавчора"]

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

def format_published_date(text, now=None):
    if not text or RELATIVE_RE.search(text):
        return text
    match = FULL_DATE_RE.search(text)
    if match is None:
        return text
    if now is None:
        now = datetime.now(timezone.utc)
    published = parse_published_date(match.group(0), now)
    if published is None:
        return text
    today = now.astimezone(KYIV).date()
    days_ago = (today - published).days
    if 0 <= days_ago < len(RELATIVE_DAYS):
        label = RELATIVE_DAYS[days_ago]
    else:
        label = f"{published.day} {MONTHS[published.month - 1]}"
        if published.year != today.year:
            label += f" {published.year} р."
    prefix = text[:match.start()]
    if prefix:
        label = label[0].lower() + label[1:]
    return prefix + label + YEAR_SUFFIX_RE.sub("", text[match.end():])

@one_request_at_a_time
def scrape(query, page=1, min_price=None, max_price=None, sort="new", city=None, state=None):
    location = CITIES[city]["slug"] if city else "list"
    url = f"https://www.olx.ua/uk/{location}/q-{query}/"

    params = {
        "page": page,
        "search[order]": SORTS[sort],
    }
    if min_price is not None:
        params["search[filter_float_price:from]"] = min_price
    if max_price is not None:
        params["search[filter_float_price:to]"] = max_price
    if state:
        params["search[filter_enum_state][0]"] = state
    try:
        response = requests.get(url, params=params, timeout=10, impersonate="chrome")
    except requests.exceptions.Timeout as e:
        raise OlxError("таймаут") from e
    except Exception as e:
        raise OlxError("мережа") from e

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser', parse_only=LISTING_ONLY)
        grid = soup.select_one('[data-testid="listing-grid"]') or soup
        elements = grid.select('[data-cy="l-card"]')
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
    raise OlxError(f"HTTP {response.status_code}")

@one_request_at_a_time
def scrape_details(link):
    try:
        response = requests.get(link, timeout=10, impersonate="chrome")
    except Exception:
        return {"description": None, "photos": [], "price": None}
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        description = soup.select_one('[data-cy="ad_description"]')
        price = soup.select_one('[data-testid="ad-price-container"]')
        photo = soup.select('[data-testid="ad-photo"] img')
        photos = []
        for img in photo:
            src = img.get('src')
            if src:
                photos.append(clean_photo(src))
        text = description.get_text("\n", strip=True) if description else None
        if text and text.startswith("Опис"):
            text = text[len("Опис"):].strip()
        price = clean_price(price.get_text(" ", strip=True)) if price else None
        return {"description": text, "photos": photos, "price": price}
    return {"description": None, "photos": [], "price": None}

def download_photo(url):
    try:
        response = requests.get(url, timeout=10, impersonate="chrome")
    except Exception:
        return None
    if response.status_code == 200:
        return response.content
    return None
