from curl_cffi import requests
import re
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

def clean_price(price):
    cleaned = re.sub(r'\D', '', price)
    if cleaned == "":
        return None
    return int(cleaned)

def clean_photo(url):
    if url is None:
        return None
    photo = re.sub(r';s=\d+x\d+;q=\d+', ";s=1000x1000;q=90", url)
    return photo

def scrape(query, page=1):
    url = f"https://www.olx.ua/uk/list/q-{query}/?page={page}"
    try:
        response = requests.get(url, timeout=10, impersonate="chrome")
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
                    "price": cleaned_price,
                    "name" : name.text,
                    "town" : parts[0],
                    "published_date" : parts[1],
                    "photo" : photo,
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
        description = soup.select_one('[data-cy="ad_description"] div')
        photo = soup.select('[data-testid="ad-photo"] img')
        photos = []
        for img in photo:
            cleaned = clean_photo(img['src'])
            photos.append(cleaned)
        text = description.text if description else None
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
