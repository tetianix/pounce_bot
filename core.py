from scrapers.olx import scrape as olx_scrape

SOURCES = {
    "olx" : olx_scrape,
}
def search(query, page=1, sources=None):
    if sources is None:
        sources = list(SOURCES)
    results = []
    for source in sources:
        func = SOURCES[source]
        found = func(query, page)
        results.extend(found)
    return results
