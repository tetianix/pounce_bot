from datetime import datetime, timedelta, timezone
from scrapers.olx import scrape as olx_scrape, parse_published_date

SOURCES = {
    "olx" : olx_scrape,
}
PERIODS = {
    "1d": 1,
    "3d": 3,
    "7d": 7,
}
MAX_PERIOD_PAGES = 4

def search(query, page=1, sources=None, min_price=None, max_price=None, sort="new"):
    if sources is None:
        sources = list(SOURCES)
    results = []
    for source in sources:
        func = SOURCES[source]
        found = func(query, page, min_price=min_price, max_price=max_price, sort=sort)
        results.extend(found)
    return results

def sort_ads(ads, sort):
    if sort == "cheap":
        return sorted(ads, key=lambda ad: (ad["price"] is None, ad["price"] or 0))
    if sort == "expensive":
        return sorted(ads, key=lambda ad: (ad["price"] is None, -(ad["price"] or 0)))
    return sorted(ads, key=lambda ad: ad["published_at"], reverse=True)

def search_recent(query, period, min_price=None, max_price=None, sort="new", now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=PERIODS[period])
    results = []
    seen = set()
    for page in range(1, MAX_PERIOD_PAGES + 1):
        found = search(query, page, min_price=min_price, max_price=max_price, sort="new")
        new_ads = [ad for ad in found if (ad["source"], ad["id"]) not in seen]
        if not new_ads:
            break
        reached_old = False
        for ad in new_ads:
            seen.add((ad["source"], ad["id"]))
            ad["published_at"] = parse_published_date(ad["published_date"], now)
            if ad["published_at"] is None or ad["published_at"] < cutoff:
                if not ad["promoted"]:
                    reached_old = True
                continue
            results.append(ad)
        if reached_old:
            break
    return sort_ads(results, sort)
