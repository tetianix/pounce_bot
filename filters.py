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


def has_all_words(name, query):
    return split_words(query) <= split_words(name)


def filter_exact(ads, query):
    return [ad for ad in ads if has_all_words(ad['name'], query)]
