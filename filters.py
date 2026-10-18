import re

WORD_RE = re.compile(r'\w+')


def filter_by_price(ads, max_price=None, min_price=None):
    filtered = []
    for ad in ads:
        if ad['price'] is not None and (max_price is None or ad['price'] <= max_price) and (min_price is None or ad['price'] >= min_price):
            filtered.append(ad)
    return filtered


def split_words(text):
    return set(WORD_RE.findall(text.lower()))


def filter_exact(ads, query):
    words = split_words(query)
    return [ad for ad in ads if words <= split_words(ad['name'])]
