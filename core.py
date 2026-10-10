from scrapers.olx import scrape as olx_scrape

SOURCES = {
    "olx" : olx_scrape,
}
def search(query, page=1, sources=None, min_price=None, max_price=None, sort="new"):
    if sources is None:
        sources = list(SOURCES)
    results = []
    for source in sources:
        func = SOURCES[source]
        found = func(query, page, min_price=min_price, max_price=max_price, sort=sort)
        results.extend(found)
    return results
